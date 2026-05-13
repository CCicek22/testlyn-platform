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

    async def write(
        self,
        rows: list[dict],  # type: ignore[type-arg]
        *,
        poison: bool = False,
        kind: str = "samples_1s",
    ) -> None:
        """Persist a batch to the spool. `poison=True` → write to poison/.

        `kind` is a discriminator written into every spool file's header line
        so `_drain_spool` can route replayed batches to the correct BQ table.
        Phase 1 only uses "samples_1s"; future phases may add "runs_summary".
        """
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
            # First line is a header record with the kind discriminator.
            # Readers MUST check _header["_kind"] before routing to a BQ table.
            await fh.write(json.dumps({"_kind": kind}) + "\n")
            for row in rows:
                await fh.write(json.dumps(row) + "\n")

        log.warning(
            "sidecar.spooled",
            path=str(filename),
            batch_size=len(rows),
            poison=poison,
        )

    async def drain(self) -> AsyncIterator[tuple[str, list[dict]]]:  # type: ignore[type-arg]
        """Yield (kind, rows) tuples from leftover spool files (non-poison only).

        `kind` is the BQ table discriminator written by `write()` into the
        first header line of each spool file.  Callers must route to the
        correct table based on `kind`.

        The file is deleted after each successful yield (caller must not raise).
        """
        self._ensure_dirs()
        spool_files = sorted(self._dir.glob("*.jsonl"))
        if not spool_files:
            return

        log.info("spool.drain_start", file_count=len(spool_files))
        for path in spool_files:
            try:
                kind = "samples_1s"  # default for files written before R1-C2
                rows: list[dict] = []  # type: ignore[type-arg]
                async with aiofiles.open(path) as fh:
                    first = True
                    async for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        parsed = json.loads(line)
                        if first:
                            first = False
                            if "_kind" in parsed:
                                kind = parsed["_kind"]
                                assert kind == "samples_1s", (
                                    f"Unknown spool kind '{kind}' in {path} — "
                                    "only 'samples_1s' is supported in Phase 1"
                                )
                                continue  # header consumed; don't add to rows
                        rows.append(parsed)
                if rows:
                    yield kind, rows
                    # File is removed after successful yield; caller must not raise
                    # between yield and the next iteration.
                    path.unlink(missing_ok=True)
                    log.info("sidecar.spool_drained", path=str(path), rows=len(rows), kind=kind)
            except Exception as exc:
                log.error("spool.drain_error", path=str(path), error=str(exc))

    async def size_bytes(self) -> int:
        """Return total spool size in bytes (non-poison only)."""
        return self._spool_size_bytes()
