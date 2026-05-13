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


class _BQInsertError(Exception):
    """Raised when insert_rows_json returns row-level errors."""

    def __init__(self, errors: list) -> None:  # type: ignore[type-arg]
        self.errors = errors
        super().__init__(str(errors))


class _TransientBQError(Exception):
    """Network error, 429, 503 — eligible for retry."""


class _PoisonBQError(Exception):
    """Hard 4xx (schema mismatch, auth, etc.) — do not retry."""


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
        summary_json: dict | None = None,
    ) -> None:
        """Write a single row to the runs_summary table."""
        row = {
            "run_id": self._cfg.RUN_ID,
            "org_id": self._cfg.ORG_ID,
            "product": self._cfg.PRODUCT,
            "region": self._cfg.REGION,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": status,
            "summary_json": json.dumps(summary_json) if summary_json else None,
        }
        await self._insert_with_retry([row], table_id=self._cfg.summary_table_id)

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

    async def _insert_with_retry(self, rows: list[dict[str, Any]], *, table_id: str) -> None:
        try:
            await asyncio.to_thread(self._insert_rows_sync, rows, table_id)
        except _TransientBQError as exc:
            log.warning(
                "sidecar.batch_failed",
                error=str(exc),
                rows=len(rows),
                action="spooling",
            )
            await self._spool.write(rows)
            self._total_spool_incidents += 1
        except _PoisonBQError as exc:
            log.error(
                "sidecar.batch_poison",
                error=str(exc),
                rows=len(rows),
            )
            await self._spool.write(rows, poison=True)
            self._total_spool_incidents += 1

    @retry(
        retry=retry_if_exception_type(_TransientBQError),
        wait=wait_exponential(multiplier=1, min=1, max=32),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _insert_rows_sync(self, rows: list[dict[str, Any]], table_id: str) -> None:
        """Synchronous BQ insert — run via asyncio.to_thread."""
        client = self._get_client()
        try:
            errors = client.insert_rows_json(table_id, rows)
        except GoogleCloudError as exc:
            status = getattr(exc, "code", None)
            if status in _TRANSIENT_CODES or status is None:
                raise _TransientBQError(str(exc)) from exc
            raise _PoisonBQError(str(exc)) from exc

        if errors:
            # insert_rows_json returns a list of row-error dicts; treat as transient
            # unless every error is a structural schema mismatch (which would be 400-class)
            log.warning("sidecar.batch_failed", errors=errors[:3], action="retry")
            raise _TransientBQError(str(errors))

    async def _drain_spool(self) -> None:
        total = 0
        async for kind, batch in self._spool.drain():
            # Route to the correct BQ table based on the kind discriminator.
            # Phase 1 only ever spools samples_1s rows; assert to catch drift.
            assert kind == "samples_1s", f"Unexpected spool kind: {kind!r}"
            await self._insert_with_retry(batch, table_id=self._cfg.samples_table_id)
            total += len(batch)
        if total:
            log.info("sidecar.spool_drained", rows=total)
