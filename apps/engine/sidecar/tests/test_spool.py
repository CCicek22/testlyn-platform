"""Tests for the spool: write, drain, replay, and cap enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar.spool import Spool


@pytest.mark.asyncio
async def test_write_and_drain(tmp_path: Path) -> None:
    spool = Spool(str(tmp_path))
    rows = [{"run_id": "r1", "metric": "m", "count": i} for i in range(5)]
    await spool.write(rows)

    batches = [b async for b in spool.drain()]
    assert len(batches) == 1
    assert len(batches[0]) == 5
    # File should be deleted after drain
    assert list(Path(str(tmp_path)).glob("*.jsonl")) == []  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_multiple_writes_multiple_drains(tmp_path: Path) -> None:
    spool = Spool(str(tmp_path))
    await spool.write([{"n": 1}])
    await spool.write([{"n": 2}])

    batches = [b async for b in spool.drain()]
    # Two spool files → two batches (ordered by timestamp prefix)
    assert len(batches) == 2
    ns = {b[0]["n"] for b in batches}
    assert ns == {1, 2}


@pytest.mark.asyncio
async def test_drain_empty_spool(tmp_path: Path) -> None:
    spool = Spool(str(tmp_path))
    batches = [b async for b in spool.drain()]
    assert batches == []


@pytest.mark.asyncio
async def test_poison_write_does_not_appear_in_drain(tmp_path: Path) -> None:
    spool = Spool(str(tmp_path))
    await spool.write([{"poisoned": True}], poison=True)

    batches = [b async for b in spool.drain()]
    assert batches == []  # drain ignores poison/

    # But poison dir should have the file
    poison_files = list((tmp_path / "poison").glob("*.jsonl"))
    assert len(poison_files) == 1


@pytest.mark.asyncio
async def test_cap_drops_batch_when_full(tmp_path: Path) -> None:
    # Set cap to 1 byte — any write should exceed it
    _ = Spool(str(tmp_path), cap_bytes=1)  # capped spool (unused directly)
    # First write: spool is empty → allowed (size check runs before write)
    # Actually cap is 1 byte, so even the first write may be blocked if previous data exists.
    # Simulate: write one batch, then try another with a spool that's "full"
    normal_spool = Spool(str(tmp_path))
    await normal_spool.write([{"x": 1}])  # actual file now exists

    capped_spool = Spool(str(tmp_path), cap_bytes=1)
    # Now spool has data > 1 byte; next write should drop
    await capped_spool.write([{"y": 2}])

    batches = [b async for b in Spool(str(tmp_path)).drain()]
    # Only the first batch should be there
    assert len(batches) == 1
    assert batches[0][0].get("x") == 1


@pytest.mark.asyncio
async def test_size_bytes(tmp_path: Path) -> None:
    spool = Spool(str(tmp_path))
    assert await spool.size_bytes() == 0
    await spool.write([{"data": "x" * 100}])
    size = await spool.size_bytes()
    assert size > 0
