"""BigQuery writer with batching, flush, and tenacity-backed retry.

Flush triggers (whichever fires first):
  1. Buffer reaches BATCH_SIZE rows
  2. FLUSH_INTERVAL_SECONDS elapsed since last flush
  3. MAX_BUFFER_ROWS exceeded (force flush)
  4. Final flush on k6 EOF
  5. SIGTERM

On transient failure (429, 503, network): exponential backoff via tenacity,
then spool if all retries exhausted.
On hard 4xx failure (other than 429): spool to poison/.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

import structlog
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from sidecar.config import SidecarConfig
from sidecar.spool import Spool

log = structlog.get_logger(__name__)

# Transient error codes that trigger retry
_TRANSIENT_CODES = {429, 500, 503}

# Spec §5 columns sourced from k6 summary.json
_SUMMARY_AGG_KEYS = (
    "vus_max",
    "iterations",
    "http_reqs",
    "http_failed",
    "data_sent",
    "data_received",
)

# Hard-4xx reasons returned by insert_rows_json that signal poison rows.
# Per BQ docs: 'invalid' = schema mismatch / bad value.  'stopped' is NOT
# poison — it means the row was not attempted because ANOTHER row in the
# batch was invalid, and it is safe to retry.  (We also pass
# skip_invalid_rows=True so one bad row can't abort the whole batch.)
# Everything else (timeout, rate limit, backend error) is treated as
# transient.
_POISON_REASONS = frozenset({"invalid"})


def _extract_summary_aggregates(
    summary: dict[str, Any] | None,
) -> dict[str, int | None]:
    """Pull the six spec §5 aggregate columns out of a k6 summary blob.

    k6's `--summary-export` JSON wraps metrics under a top-level `metrics`
    object; each entry has shape `{ "values": { "count": n, "max": m, ... } }`.
    We extract:

      * vus_max       ← metrics.vus_max.values.max  (or .value)
      * iterations    ← metrics.iterations.values.count
      * http_reqs     ← metrics.http_reqs.values.count
      * http_failed   ← metrics.http_req_failed.values.fails (or .passes inv.)
      * data_sent     ← metrics.data_sent.values.count
      * data_received ← metrics.data_received.values.count

    Missing keys → NULL.  k6 1.x and 2.x both use this layout; recheck on
    major-version bumps (see CLAUDE.md §8 "Bumping a dependency").
    """
    out: dict[str, int | None] = dict.fromkeys(_SUMMARY_AGG_KEYS, None)
    if not summary:
        return out
    metrics = summary.get("metrics") or {}
    if not isinstance(metrics, dict):
        return out

    def _int(metric: str, *value_keys: str) -> int | None:
        m = metrics.get(metric)
        if not isinstance(m, dict):
            return None
        values = m.get("values")
        if not isinstance(values, dict):
            return None
        for key in value_keys:
            v = values.get(key)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return None
        return None

    out["vus_max"] = _int("vus_max", "max", "value")
    out["iterations"] = _int("iterations", "count")
    out["http_reqs"] = _int("http_reqs", "count")
    out["http_failed"] = _int("http_req_failed", "fails")
    out["data_sent"] = _int("data_sent", "count")
    out["data_received"] = _int("data_received", "count")
    return out


def _row_insert_id(row: dict[str, Any]) -> str:
    """Stable insertId per spec §7 — used as BQ dedup key.

    Hash on the natural identity tuple: (run_id, metric, window_start,
    tag_method, tag_status, tag_scenario, tag_group, tag_name).  Any retry
    or spool-replay of the same row will collide on this ID, so BQ ignores
    the duplicate even when the underlying buffer is replayed.
    """
    import hashlib

    parts = (
        str(row.get("run_id", "")),
        str(row.get("metric", "")),
        str(row.get("window_start", "")),
        str(row.get("tag_method", "")),
        str(row.get("tag_status", "")),
        str(row.get("tag_scenario", "")),
        str(row.get("tag_group", "")),
        str(row.get("tag_name", "")),
    )
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


class _BQInsertError(Exception):
    """Raised when insert_rows_json returns row-level errors."""

    def __init__(self, errors: list) -> None:  # type: ignore[type-arg]
        self.errors = errors
        super().__init__(str(errors))


class _TransientBQError(Exception):
    """Network error, 429, 503 — eligible for retry."""


class _PoisonBQError(Exception):
    """Hard 4xx (schema mismatch, auth, etc.) — do not retry."""


class _PartialPoisonError(Exception):
    """Row-level errors classified: some poison, some still good.

    Raised from `_insert_rows_sync` when `insert_rows_json` returns row errors
    that single out a subset of rows as unrecoverable.  The caller splits the
    batch — poison rows go to `poison/`, surviving rows are re-inserted.
    """

    def __init__(
        self,
        *,
        poison_rows: list[dict[str, Any]],
        surviving_rows: list[dict[str, Any]],
    ) -> None:
        self.poison_rows = poison_rows
        self.surviving_rows = surviving_rows
        super().__init__(
            f"partial poison: {len(poison_rows)} poison, {len(surviving_rows)} surviving"
        )


class BQWriter:
    """Buffers WindowSample rows and flushes them to BigQuery."""

    def __init__(self, cfg: SidecarConfig, *, spool: Spool) -> None:
        self._cfg = cfg
        self._spool = spool
        self._buffer: list[dict[str, Any]] = []
        self._last_flush_ts = time.monotonic()
        self._total_rows_sent = 0
        self._total_batches = 0
        self._total_spool_incidents = 0
        self._client: bigquery.Client | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    def _get_client(self) -> bigquery.Client:
        if self._client is None:
            kwargs: dict[str, Any] = {"project": self._cfg.GCP_PROJECT}
            if self._cfg.BIGQUERY_EMULATOR_HOST:
                kwargs["client_options"] = {"api_endpoint": self._cfg.BIGQUERY_EMULATOR_HOST}
            self._client = bigquery.Client(**kwargs)
        return self._client

    async def start(self) -> None:
        """Start the background periodic-flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush_loop())
        # Drain any leftover spool from a previous crashed run
        await self._drain_spool()

    async def stop(self) -> None:
        """Stop background flush; final flush is caller's responsibility."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, row: dict[str, Any]) -> None:
        """Add a row to the buffer; force-flush if MAX_BUFFER_ROWS hit."""
        self._buffer.append(row)
        if len(self._buffer) >= self._cfg.MAX_BUFFER_ROWS:
            log.warning("bq_writer.force_flush_max_buffer", size=len(self._buffer))
            await self._flush()
        elif len(self._buffer) >= self._cfg.BATCH_SIZE:
            await self._flush()

    async def final_flush(self) -> None:
        """Flush everything remaining in the buffer. Call after k6 EOF."""
        await self._flush()

    async def write_runs_summary(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        summary_json: dict[str, Any] | None = None,
    ) -> None:
        """Write a single row to the runs_summary table.

        Per spec §5 the row carries six aggregate columns sourced from k6's
        `--summary-export` JSON (`vus_max`, `iterations`, `http_reqs`,
        `http_failed`, `data_sent`, `data_received`).  If `summary_json` is
        None or any key is missing, the column is written as NULL — a warning
        is logged so an operator can spot misconfigured engine containers.
        """
        aggregates = _extract_summary_aggregates(summary_json)
        if summary_json is None:
            log.warning(
                "sidecar.runs_summary_no_blob",
                run_id=self._cfg.RUN_ID,
            )

        row: dict[str, Any] = {
            "run_id": self._cfg.RUN_ID,
            "org_id": self._cfg.ORG_ID,
            "product": self._cfg.PRODUCT,
            "region": self._cfg.REGION,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": status,
            "summary_json": json.dumps(summary_json) if summary_json else None,
            **aggregates,
        }
        # kind="runs_summary" so a spooled summary row replays into the
        # runs_summary table, not samples_1s (where it would poison).
        await self._insert_with_retry(
            [row], table_id=self._cfg.summary_table_id, kind="runs_summary"
        )

    async def stats(self) -> dict[str, int]:
        return {
            "total_rows_sent": self._total_rows_sent,
            "total_batches": self._total_batches,
            "total_spool_incidents": self._total_spool_incidents,
            "buffer_size": len(self._buffer),
        }

    # --- internal ---

    async def _periodic_flush_loop(self) -> None:
        interval = self._cfg.FLUSH_INTERVAL_SECONDS
        while self._running:
            await asyncio.sleep(interval)
            if self._buffer:
                elapsed = time.monotonic() - self._last_flush_ts
                if elapsed >= interval:
                    await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush_ts = time.monotonic()

        t0 = time.monotonic()
        await self._insert_with_retry(batch, table_id=self._cfg.samples_table_id)
        latency_ms = (time.monotonic() - t0) * 1000
        log.info(
            "sidecar.batch_flushed",
            rows=len(batch),
            latency_ms=round(latency_ms, 1),
        )
        self._total_rows_sent += len(batch)
        self._total_batches += 1

    async def _insert_with_retry(
        self,
        rows: list[dict[str, Any]],
        *,
        table_id: str,
        kind: str = "samples_1s",
    ) -> None:
        try:
            await asyncio.to_thread(self._insert_rows_sync, rows, table_id)
        except _TransientBQError as exc:
            log.warning(
                "sidecar.batch_failed",
                error=str(exc),
                rows=len(rows),
                action="spooling",
            )
            await self._spool.write(rows, kind=kind)
            self._total_spool_incidents += 1
        except _PoisonBQError as exc:
            log.error(
                "sidecar.batch_poison",
                error=str(exc),
                rows=len(rows),
            )
            await self._spool.write(rows, poison=True, kind=kind)
            self._total_spool_incidents += 1
        except _PartialPoisonError as exc:
            # Split: poison rows go to poison/, surviving rows retry inline.
            log.warning(
                "sidecar.batch_split",
                poison_count=len(exc.poison_rows),
                surviving_count=len(exc.surviving_rows),
            )
            if exc.poison_rows:
                await self._spool.write(exc.poison_rows, poison=True, kind=kind)
                self._total_spool_incidents += 1
            if exc.surviving_rows:
                # Recurse: the surviving subset may itself fail and re-split.
                await self._insert_with_retry(
                    exc.surviving_rows, table_id=table_id, kind=kind
                )

    @retry(
        retry=retry_if_exception_type(_TransientBQError),
        wait=wait_exponential(multiplier=1, min=1, max=32),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _insert_rows_sync(self, rows: list[dict[str, Any]], table_id: str) -> None:
        """Synchronous BQ insert — run via asyncio.to_thread.

        Row IDs are computed from the natural identity tuple so retries +
        spool replays dedup at BQ ingestion (spec §7).
        """
        client = self._get_client()
        row_ids = [_row_insert_id(r) for r in rows]
        try:
            # skip_invalid_rows=True: insert all valid rows even when some rows
            # are invalid.  Without it one bad row 'stops' the entire batch and
            # a 5000-row flush would be lost to poison/ wholesale.
            errors = client.insert_rows_json(
                table_id, rows, row_ids=row_ids, skip_invalid_rows=True
            )
        except GoogleCloudError as exc:
            status = getattr(exc, "code", None)
            if status in _TRANSIENT_CODES or status is None:
                raise _TransientBQError(str(exc)) from exc
            raise _PoisonBQError(str(exc)) from exc

        if errors:
            # Per BQ docs, `errors` is a list of {index, errors: [{reason, ...}]}.
            # With skip_invalid_rows=True, rows NOT listed in `errors` were
            # inserted successfully.  Split the errored rows into poison
            # ('invalid' — will never succeed) vs retriable ('stopped',
            # timeouts, etc. — safe to retry; insertId dedup absorbs any
            # double-send).
            poison_idx: set[int] = set()
            error_idx: set[int] = set()
            for err in errors:
                idx = err.get("index")
                if idx is None:
                    continue
                error_idx.add(int(idx))
                reasons = {e.get("reason") for e in (err.get("errors") or [])}
                if reasons & _POISON_REASONS:
                    poison_idx.add(int(idx))
            retriable_idx = error_idx - poison_idx

            if poison_idx == set(range(len(rows))):
                # Every row is poison — short-circuit to the poison branch.
                log.error("sidecar.batch_all_poison", errors=errors[:3])
                raise _PoisonBQError(str(errors))

            if poison_idx:
                poison_rows = [rows[i] for i in sorted(poison_idx)]
                surviving = [rows[i] for i in sorted(retriable_idx)]
                log.warning(
                    "sidecar.batch_partial_poison",
                    poison=len(poison_rows),
                    surviving=len(surviving),
                    sample_errors=errors[:3],
                )
                raise _PartialPoisonError(
                    poison_rows=poison_rows,
                    surviving_rows=surviving,
                )

            # No row was classified poison → retry just the errored rows.
            log.warning("sidecar.batch_failed", errors=errors[:3], action="retry")
            raise _TransientBQError(str(errors))

    async def _drain_spool(self) -> None:
        total = 0
        async for kind, batch in self._spool.drain():
            # Route to the correct BQ table based on the kind discriminator.
            table_id = (
                self._cfg.summary_table_id
                if kind == "runs_summary"
                else self._cfg.samples_table_id
            )
            await self._insert_with_retry(batch, table_id=table_id, kind=kind)
            total += len(batch)
        if total:
            log.info("sidecar.spool_drained", rows=total)
