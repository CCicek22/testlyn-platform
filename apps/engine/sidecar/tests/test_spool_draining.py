"""Tests for spool .draining rename + dead-letter recovery (audit fix #10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar.spool import Spool


@pytest.mark.asyncio
async def test_drain_renames_before_yield(tmp_path: Path) -> None:
    """While drain() is yielding, the original file should be `.draining`."""
    spool = Spool(str(tmp_path))
    await spool.write([{"n": 1}])
    initial = list(tmp_path.glob("*.jsonl"))  # noqa: ASYNC240
    assert len(initial) == 1

    seen_draining = False
    async for _kind, _rows in spool.drain():
        # At this point the original .jsonl should be renamed to .jsonl.draining
        draining = list(tmp_path.glob("*.jsonl.draining"))  # noqa: ASYNC240
        if draining:
            seen_draining = True

    assert seen_draining, "spool file was never observed in .draining state"
    # After drain completes successfully, no .draining file remains.
    assert list(tmp_path.glob("*.jsonl.draining")) == []  # noqa: ASYNC240
    assert list(tmp_path.glob("*.jsonl")) == []  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_orphan_draining_replays_once_then_dead_letters(tmp_path: Path) -> None:
    """A leftover .jsonl.draining from a prior crash gets one retry, then dead."""
    spool = Spool(str(tmp_path))
    await spool.write([{"n": 99}])
    # Simulate a crash: pretend drain started but never finished — rename by hand.
    original = next(tmp_path.glob("*.jsonl"))  # noqa: ASYNC240
    orphan = original.with_suffix(original.suffix + ".draining")
    original.rename(orphan)

    # Now drain() should pick it up and yield it.  Caller (this test) does NOT
    # delete the .draining file → spool should dead-letter it.
    yielded: list[list[dict]] = []  # type: ignore[type-arg]
    async for _kind, rows in spool.drain():
        yielded.append(rows)
        # Re-create the .draining file so spool sees the "still here" state.
        # (drain() unlinks after yield; we want to simulate a fresh crash.)
        orphan.write_text(orphan.name)  # any content — the dead_letter check
        # only cares about existence.

    assert yielded, "leftover .draining should be replayed once"
    # After replay where caller "failed", dead-letter dir should contain the file.
    dead = list((tmp_path / "dead").glob("*"))
    assert dead, "twice-failed .draining file should be quarantined to dead/"
