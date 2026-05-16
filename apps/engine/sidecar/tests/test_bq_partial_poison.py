"""Tests for row-level error classification (audit fix #9).

Asserts that a mixed batch (some 'invalid' rows + some salvageable rows) is
split: poison rows go to the poison spool, surviving rows are re-inserted.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidecar.bq_writer import BQWriter
from sidecar.config import SidecarConfig
from sidecar.spool import Spool


def _cfg(tmp_path: Path) -> SidecarConfig:
    return SidecarConfig(
        RUN_ID="r1",
        ORG_ID="o1",
        GCP_PROJECT="proj",
        BATCH_SIZE=10,
        SPOOL_DIR=str(tmp_path / "spool"),
    )


@pytest.mark.asyncio
async def test_partial_poison_splits_batch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    spool = Spool(str(tmp_path / "spool"))
    writer = BQWriter(cfg, spool=spool)

    poison_rows: list[dict] = []  # type: ignore[type-arg]

    async def fake_spool_write(rows, *, poison=False, kind="samples_1s"):  # type: ignore[no-untyped-def]
        if poison:
            poison_rows.extend(rows)

    # First call returns row-level errors for rows 0 and 2 (poison); rows 1 + 3
    # are salvageable.  Second call (the retry on the surviving subset) succeeds.
    call_count = {"n": 0}

    def fake_insert_rows_json(table_id, rows, row_ids=None):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] == 1:
            assert len(rows) == 4
            return [
                {"index": 0, "errors": [{"reason": "invalid", "message": "bad schema"}]},
                {"index": 2, "errors": [{"reason": "invalid", "message": "bad value"}]},
            ]
        return []

    mock_client = MagicMock()
    mock_client.insert_rows_json.side_effect = fake_insert_rows_json
    writer._client = mock_client

    with patch.object(spool, "write", side_effect=fake_spool_write):
        with patch.object(writer, "_drain_spool", new_callable=AsyncMock):
            await writer.start()
            await writer.stop()

            writer._buffer = [
                {"run_id": "r1", "metric": "m", "n": i, "window_start": str(i)}
                for i in range(4)
            ]
            await writer._flush()

    # Two rows quarantined as poison
    assert len(poison_rows) == 2
    assert {r["n"] for r in poison_rows} == {0, 2}
    # Both BQ calls happened (initial + retry on surviving subset)
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_row_ids_are_passed(tmp_path: Path) -> None:
    """audit fix #8: insert_rows_json must receive a row_ids kwarg for dedup."""
    cfg = _cfg(tmp_path)
    spool = Spool(str(tmp_path / "spool"))
    writer = BQWriter(cfg, spool=spool)

    seen_row_ids: list[list[str]] = []

    def fake_insert_rows_json(table_id, rows, row_ids=None):  # type: ignore[no-untyped-def]
        seen_row_ids.append(row_ids or [])
        return []

    mock_client = MagicMock()
    mock_client.insert_rows_json.side_effect = fake_insert_rows_json
    writer._client = mock_client

    with patch.object(writer, "_drain_spool", new_callable=AsyncMock):
        await writer.start()
        await writer.stop()

        writer._buffer = [
            {"run_id": "r1", "metric": "m", "window_start": "2026-05-16T00:00:00"},
            {"run_id": "r1", "metric": "m", "window_start": "2026-05-16T00:00:01"},
        ]
        await writer._flush()

    assert seen_row_ids
    assert len(seen_row_ids[0]) == 2
    # Distinct window_start → distinct insertId
    assert seen_row_ids[0][0] != seen_row_ids[0][1]
    # Stable: same row → same hash
    assert all(isinstance(rid, str) and len(rid) == 40 for rid in seen_row_ids[0])
