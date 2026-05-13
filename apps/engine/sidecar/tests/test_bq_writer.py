"""Tests for the BQ writer: batching, flush, retry, and spool fallback.

Uses mocks for the BigQuery client so no real GCP connection is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidecar.bq_writer import BQWriter, _TransientBQError
from sidecar.config import SidecarConfig
from sidecar.spool import Spool


def _make_cfg(tmp_path: Path, batch_size: int = 5, flush_interval: float = 60.0) -> SidecarConfig:
    return SidecarConfig(
        RUN_ID="r1",
        ORG_ID="o1",
        GCP_PROJECT="proj",
        BATCH_SIZE=batch_size,
        FLUSH_INTERVAL_SECONDS=flush_interval,
        MAX_BUFFER_ROWS=50000,
        SPOOL_DIR=str(tmp_path / "spool"),
    )


def _make_row(n: int = 0) -> dict[str, Any]:
    return {"run_id": "r1", "metric": f"m_{n}", "count": 1}


class TestBatching:
    @pytest.mark.asyncio
    async def test_flush_at_batch_size(self, tmp_path: Path) -> None:
        """Writer should flush exactly when BATCH_SIZE rows accumulated."""
        cfg = _make_cfg(tmp_path, batch_size=3)
        spool = Spool(str(tmp_path / "spool"))
        writer = BQWriter(cfg, spool=spool)

        flushed: list[list[dict]] = []

        async def fake_insert(rows: list, *, table_id: str) -> None:
            flushed.append(rows)

        with patch.object(writer, "_insert_with_retry", side_effect=fake_insert):
            # No flush yet after draining spool
            await writer.start()
            await writer.stop()

            # Enqueue 2 rows — no flush yet (< batch_size)
            await writer.enqueue(_make_row(0))
            await writer.enqueue(_make_row(1))
            assert len(flushed) == 0

            # 3rd row triggers flush
            await writer.enqueue(_make_row(2))
            assert len(flushed) == 1
            assert len(flushed[0]) == 3

    @pytest.mark.asyncio
    async def test_final_flush_sends_remaining(self, tmp_path: Path) -> None:
        cfg = _make_cfg(tmp_path, batch_size=100)
        spool = Spool(str(tmp_path / "spool"))
        writer = BQWriter(cfg, spool=spool)

        flushed: list[list[dict]] = []

        async def fake_insert(rows: list, *, table_id: str) -> None:
            flushed.append(rows)

        with patch.object(writer, "_insert_with_retry", side_effect=fake_insert):
            await writer.start()
            await writer.stop()

            await writer.enqueue(_make_row(0))
            await writer.enqueue(_make_row(1))
            assert len(flushed) == 0

            await writer.final_flush()
            assert len(flushed) == 1
            assert len(flushed[0]) == 2


class TestRetryAndSpool:
    @pytest.mark.asyncio
    async def test_transient_error_spools_after_retries(self, tmp_path: Path) -> None:
        """When all tenacity retries fail, the batch is spooled."""
        cfg = _make_cfg(tmp_path, batch_size=2)
        spool = Spool(str(tmp_path / "spool"))
        writer = BQWriter(cfg, spool=spool)

        spooled: list[list[dict]] = []

        async def fake_spool_write(rows: list, *, poison: bool = False) -> None:
            spooled.append(rows)

        with patch.object(spool, "write", side_effect=fake_spool_write):
            # Patch _insert_rows_sync to always raise _TransientBQError
            # (simulates tenacity exhausting all 6 retries and re-raising)
            with patch.object(
                writer,
                "_insert_rows_sync",
                side_effect=_TransientBQError("503 service unavailable"),
            ):
                with patch.object(writer, "_drain_spool", new_callable=AsyncMock):
                    await writer.start()
                    await writer.stop()

                    # Force a flush
                    writer._buffer = [_make_row(0), _make_row(1)]
                    await writer._flush()

        # After exhaused retries the batch must be in spool
        assert len(spooled) == 1

    @pytest.mark.asyncio
    async def test_poison_error_spools_to_poison(self, tmp_path: Path) -> None:
        cfg = _make_cfg(tmp_path, batch_size=1)
        spool = Spool(str(tmp_path / "spool"))
        writer = BQWriter(cfg, spool=spool)

        poison_calls: list[dict] = []

        async def fake_spool_write(rows: list, *, poison: bool = False) -> None:
            if poison:
                poison_calls.extend(rows)

        with patch.object(spool, "write", side_effect=fake_spool_write):
            # Simulate a hard 400 error (schema mismatch)
            from google.cloud.exceptions import BadRequest

            mock_client = MagicMock()
            mock_client.insert_rows_json.side_effect = BadRequest("invalid field")
            writer._client = mock_client

            with patch.object(writer, "_drain_spool", new_callable=AsyncMock):
                await writer.start()
                await writer.stop()

                writer._buffer = [_make_row(0)]
                await writer._flush()

        assert len(poison_calls) == 1


class TestSpoolReplay:
    @pytest.mark.asyncio
    async def test_spool_drain_replays_on_startup(self, tmp_path: Path) -> None:
        """If spool files exist from a previous crash, drain() replays them."""
        spool_dir = tmp_path / "spool"
        spool = Spool(str(spool_dir))

        # Pre-populate spool with one batch
        await spool.write([_make_row(99)])

        cfg = _make_cfg(tmp_path, batch_size=100)
        writer = BQWriter(cfg, spool=spool)

        replayed: list[list[dict]] = []

        async def fake_insert(rows: list, *, table_id: str) -> None:
            replayed.append(rows)

        with patch.object(writer, "_insert_with_retry", side_effect=fake_insert):
            await writer.start()
            await writer.stop()

        assert len(replayed) == 1
        assert replayed[0][0]["metric"] == "m_99"
