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
import logging
import os
import signal
from datetime import UTC, datetime

import structlog

from sidecar.bq_writer import BQWriter
from sidecar.config import SidecarConfig
from sidecar.health import HealthServer
from sidecar.parsers.k6 import K6Parser
from sidecar.spool import Spool
from sidecar.windows import WindowAggregator


def _configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
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
        k6_output_path=cfg.K6_OUTPUT_PATH,
        batch_size=cfg.BATCH_SIZE,
        flush_interval_seconds=cfg.FLUSH_INTERVAL_SECONDS,
        window_seconds=cfg.WINDOW_SECONDS,
        spool_dir=cfg.SPOOL_DIR,
        emulator=cfg.BIGQUERY_EMULATOR_HOST,
    )

    spool = Spool(cfg.SPOOL_DIR, cap_bytes=cfg.SPOOL_MAX_BYTES)
    writer = BQWriter(cfg, spool=spool)
    health = HealthServer(port=cfg.HEALTH_PORT)
    parser = K6Parser(cfg.K6_OUTPUT_PATH)
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

        # Determine status from environment variable set by entrypoint.sh
        k6_exit = int(os.environ.get("K6_EXIT_CODE", "0"))
        status = "completed" if k6_exit == 0 else "failed"

        await writer.write_runs_summary(
            started_at=started_at,
            finished_at=finished_at,
            status=status,
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
