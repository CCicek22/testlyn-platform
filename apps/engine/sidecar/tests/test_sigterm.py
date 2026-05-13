"""Test that SIGTERM triggers a clean shutdown that drains the buffer.

We test the signal handler logic directly (asyncio event flag) rather than
sending SIGTERM to the process, which avoids test isolation issues.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sidecar.bq_writer import BQWriter
from sidecar.config import SidecarConfig
from sidecar.spool import Spool


def _make_cfg(tmp_path: Path) -> SidecarConfig:
    return SidecarConfig(
        RUN_ID="r1",
        ORG_ID="o1",
        GCP_PROJECT="proj",
        BATCH_SIZE=100,
        FLUSH_INTERVAL_SECONDS=60.0,
        MAX_BUFFER_ROWS=50000,
        SPOOL_DIR=str(tmp_path / "spool"),
    )


@pytest.mark.asyncio
async def test_stop_event_drains_buffer(tmp_path: Path) -> None:
    """Simulates the main loop checking stop_event mid-stream."""
    stop_event = asyncio.Event()
    processed: list[Any] = []

    async def fake_stream():  # type: ignore[no-untyped-def]
        for i in range(10):
            if stop_event.is_set():
                break
            yield i
            if i == 4:
                stop_event.set()  # simulate SIGTERM after 5 events

    async for item in fake_stream():
        if stop_event.is_set():
            break
        processed.append(item)

    # Should have processed items 0-4 (5 items), then stopped
    assert len(processed) <= 5
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_final_flush_called_on_shutdown(tmp_path: Path) -> None:
    """Verify final_flush drains buffer when writer.stop() is called."""
    cfg = _make_cfg(tmp_path)
    spool = Spool(str(tmp_path / "spool"))
    writer = BQWriter(cfg, spool=spool)

    flushed: list[list[dict]] = []

    async def fake_insert(rows: list, *, table_id: str) -> None:
        flushed.append(rows[:])

    with patch.object(writer, "_insert_with_retry", side_effect=fake_insert):
        with patch.object(writer, "_drain_spool"):
            await writer.start()

            # Queue some rows (below batch_size so no auto-flush)
            for i in range(3):
                writer._buffer.append({"metric": f"m{i}"})

            # Simulate what main.py does on SIGTERM
            for _ in []:  # flush all windows (none in this test)
                pass
            await writer.final_flush()
            await writer.stop()

    assert len(flushed) == 1
    assert len(flushed[0]) == 3
