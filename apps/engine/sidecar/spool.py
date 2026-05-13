"""Fallback spool — writes undeliverable BQ batches to /tmp/spool/.

On sidecar startup, drain() replays any leftover spool files. On BQ failure,
write() persists the batch. A poison/ subdirectory holds batches that hit
unrecoverable 4xx errors.

Spool cap: 1 GiB on /tmp/spool before we emit a warning and drop. This bounds
the worst-case sidecar memory/disk footprint per the spec §9 budget.
"""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles
import aiofiles.os
import structlog

log = structlog.get_logger(__name__)

_SPOOL_CAP_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB


class Spool:
    """JSON-shard spool with async write and sync-safe replay."""

    _counter = itertools.count()

    def __init__(self, spool_dir: str, cap_bytes: int = _SPOOL_CAP_BYTES) -> None:
        self._dir = Path(spool_dir)
        self._poison_dir = self._dir / "poison"
        self._cap = cap_bytes

    def _ensure_dirs(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._poison_dir.mkdir(parents=True, exist_ok=True)

    def _spool_size_bytes(self) -> int:
        total = 0
        for p in self._dir.rglob("*.jsonl"):
            try:
                total += p.stat().st_size
            except OSError:
                pass
        return total

    async def write(self, rows: list[dict], *, poison: bool = False) -> None:  # type: ignore[type-arg]
        """Persist a batch to the spool. `poison=True` → write to poison/."""
        self._ensure_dirs()

        current_size = self._spool_size_bytes()
        if current_size >= self._cap and not poison:
            log.warning(
                "spool.cap_exceeded_drop",
                spool_size_bytes=current_size,
                cap_bytes=self._cap,
                dropped_rows=len(rows),
            )
            return

        target_dir = self._poison_dir if poison else self._dir
        seq = next(Spool._counter)
        filename = target_dir / f"{int(time.time() * 1000)}_{seq:06d}.jsonl"

        async with aiofiles.open(filename, "w") as fh:
            for row in rows:
                await fh.write(json.dumps(row) + "\n")

        log.warning(
            "sidecar.spooled",
            path=str(filename),
            batch_size=len(rows),
            poison=poison,
        )

    async def drain(self) -> AsyncIterator[list[dict]]:  # type: ignore[type-arg]
        """Yield batches from leftover spool files (non-poison only).

        Each yielded batch should be re-sent to BQ. After yielding, the
        caller is responsible for deleting the file on success (via `mark_done`).
        """
        self._ensure_dirs()
        spool_files = sorted(self._dir.glob("*.jsonl"))
        if not spool_files:
            return

        log.info("spool.drain_start", file_count=len(spool_files))
        for path in spool_files:
            try:
                rows = []
                async with aiofiles.open(path) as fh:
                    async for line in fh:
                        line = line.strip()
                        if line:
                            rows.append(json.loads(line))
                if rows:
                    yield rows
                    # Caller signals success by deleting; we remove it here
                    # after yield returns without exception
                    path.unlink(missing_ok=True)
                    log.info("sidecar.spool_drained", path=str(path), rows=len(rows))
            except Exception as exc:
                log.error("spool.drain_error", path=str(path), error=str(exc))

    async def size_bytes(self) -> int:
        """Return total spool size in bytes (non-poison only)."""
        return self._spool_size_bytes()
