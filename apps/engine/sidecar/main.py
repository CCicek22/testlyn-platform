"""Async CLI entrypoint for the Testlyn BQ sidecar.

Lifecycle:
  1. Load config from env
  2. Configure structlog
  3. Start health server
  4. Start BQ writer (drains spool from previous crash)
  5. Mark health ready
  6. Stream k6 JSONL → windows → writer
  7. On k6 EOF: flush all remaining windows, final BQ flush
  8. Write runs_summary row
  9. Log shutdown stats and exit

SIGTERM handling:
  SIGTERM sets a flag that causes the main loop to break after the current
  sample. The finally block ensures flush_all + final_flush always runs,
  so the buffer is drained within 30 seconds as required by spec §8.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from sidecar.bq_writer import BQWriter
from sidecar.config import SidecarConfig
from sidecar.health import HealthServer
from sidecar.parsers.axe import AxeParser
from sidecar.parsers.base import Parser
from sidecar.parsers.k6 import K6Parser
from sidecar.parsers.playwright import PlaywrightParser
from sidecar.spool import Spool
from sidecar.windows import WindowAggregator


def _build_parser(cfg: SidecarConfig) -> Parser:
    """Dispatch on cfg.PARSER (k6 | axe | playwright)."""
    name = cfg.PARSER.lower()
    if name == "k6":
        return K6Parser(cfg.input_path)
    if name == "axe":
        return AxeParser(cfg.input_path)
    if name == "playwright":
        return PlaywrightParser(cfg.input_path)
    raise ValueError(f"Unknown PARSER value: {cfg.PARSER!r}")


def _read_summary_json(path: str) -> dict[str, Any] | None:
    """Read k6 --summary-export JSON if present; return None on any error."""
    try:
        data: dict[str, Any] = json.loads(Path(path).read_text())
        return data
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None


async def _await_exit_code(
    path: str,
    log: Any,
    *,
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.1,
) -> int:
    """Wait up to `timeout_s` for the entrypoint to write the exit-code file.

    The entrypoint may not have written it yet when the sidecar reaches the
    runs_summary stage (race between k6 EOF and the trap firing).  Poll the
    file, then fall back to env / 0.
    """
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if Path(path).exists():  # noqa: ASYNC240 — single stat, no blocking I/O
            return _read_exit_code(path)
        await asyncio.sleep(poll_interval_s)
    log.warning("sidecar.exit_code_timeout", path=path)
    return _read_exit_code(path)


def _read_exit_code(path: str, default: int = 0) -> int:
    """Read the integer exit code the engine entrypoint wrote on workload finish.

    Falls back to the K6_EXIT_CODE env var (legacy path) and then `default`.
    """
    try:
        raw = Path(path).read_text().strip()
        if raw:
            return int(raw)
    except (OSError, ValueError):
        pass
    env = os.environ.get("K6_EXIT_CODE")
    if env is not None:
        try:
            return int(env)
        except ValueError:
            return default
    return default


def _configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            # NB: no add_logger_name — it reads logger.name, which the
            # PrintLogger produced by PrintLoggerFactory does not have, so it
            # raised AttributeError on the first log call and crashed the
            # sidecar at startup.
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


async def main() -> None:
    cfg = SidecarConfig()  # type: ignore[call-arg]  # all required fields must be in env
    _configure_logging(cfg.LOG_LEVEL)
    log = structlog.get_logger("sidecar.main")

    log.info(
        "sidecar.started",
        run_id=cfg.RUN_ID,
        org_id=cfg.ORG_ID,
        product=cfg.PRODUCT,
        region=cfg.REGION,
        bq_dataset=cfg.BQ_DATASET,
        parser=cfg.PARSER,
        input_path=cfg.input_path,
        batch_size=cfg.BATCH_SIZE,
        flush_interval_seconds=cfg.FLUSH_INTERVAL_SECONDS,
        window_seconds=cfg.WINDOW_SECONDS,
        spool_dir=cfg.SPOOL_DIR,
        emulator=cfg.BIGQUERY_EMULATOR_HOST,
    )

    spool = Spool(cfg.SPOOL_DIR, cap_bytes=cfg.SPOOL_MAX_BYTES)
    writer = BQWriter(cfg, spool=spool)
    health = HealthServer(port=cfg.HEALTH_PORT)
    parser = _build_parser(cfg)
    aggregator = WindowAggregator(
        run_id=cfg.RUN_ID,
        org_id=cfg.ORG_ID,
        product=cfg.PRODUCT,
        region=cfg.REGION,
        window_seconds=cfg.WINDOW_SECONDS,
    )

    # SIGTERM → set a stop flag; loop drains and exits cleanly
    stop_event = asyncio.Event()

    def _handle_sigterm() -> None:
        log.info("sidecar.sigterm_received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

    started_at = datetime.now(tz=UTC)
    status = "failed"

    await health.start()
    await writer.start()
    health.mark_ready()

    try:
        async for event in parser.stream():
            if stop_event.is_set():
                break
            closed_windows = aggregator.add(event)
            for ws in closed_windows:
                await writer.enqueue(ws.to_bq_row())

        # k6 closed the pipe (or SIGTERM) — flush remaining windows
        for ws in aggregator.flush_all():
            await writer.enqueue(ws.to_bq_row())

        await writer.final_flush()

        finished_at = datetime.now(tz=UTC)

        # Read k6 exit code from the file the entrypoint writes AFTER k6 finishes
        # (env-var-at-startup race is fixed; see entrypoint.sh).  Poll briefly
        # in case the entrypoint is still flushing it.
        k6_exit = await _await_exit_code(cfg.EXIT_CODE_PATH, log)
        status = "completed" if k6_exit == 0 else "failed"

        summary_blob = _read_summary_json(cfg.K6_SUMMARY_PATH)
        if summary_blob is None and cfg.PARSER == "k6":
            log.warning(
                "sidecar.summary_missing",
                summary_path=cfg.K6_SUMMARY_PATH,
            )

        await writer.write_runs_summary(
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            summary_json=summary_blob,
        )

        stats = await writer.stats()
        log.info(
            "sidecar.shutdown",
            status=status,
            **stats,
        )

    finally:
        await writer.stop()
        await health.stop()


def entry() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    entry()
