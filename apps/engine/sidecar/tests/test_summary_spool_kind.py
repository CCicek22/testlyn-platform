"""Review-finding tests: runs_summary rows must spool + replay with
kind="runs_summary" so they route back to the runs_summary table — replaying
them into samples_1s poisoned the batch and lost the summary on any BQ blip
at end-of-run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sidecar.bq_writer import BQWriter, _TransientBQError
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
async def test_summary_spools_with_runs_summary_kind(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    spool = Spool(str(tmp_path / "spool"))
    writer = BQWriter(cfg, spool=spool)

    def _always_transient(rows, table_id):  # type: ignore[no-untyped-def]
        raise _TransientBQError("bq down")

    with patch.object(writer, "_insert_rows_sync", side_effect=_always_transient):
        await writer.write_runs_summary(
            started_at=datetime.now(tz=UTC),
            finished_at=datetime.now(tz=UTC),
            status="completed",
            summary_json=None,
        )

    files = sorted((tmp_path / "spool").glob("*.jsonl"))
    assert len(files) == 1
    header = files[0].read_text().splitlines()[0]
    assert '"_kind": "runs_summary"' in header


@pytest.mark.asyncio
async def test_drain_routes_summary_kind_to_summary_table(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    spool = Spool(str(tmp_path / "spool"))

    # Pre-spool one batch of each kind (as a crashed previous run would have).
    await spool.write([{"run_id": "r1", "metric": "m"}], kind="samples_1s")
    await spool.write([{"run_id": "r1", "status": "completed"}], kind="runs_summary")

    writer = BQWriter(cfg, spool=spool)
    inserted: list[tuple[str, list]] = []  # type: ignore[type-arg]

    def _record(rows, table_id):  # type: ignore[no-untyped-def]
        inserted.append((table_id, rows))

    with patch.object(writer, "_insert_rows_sync", side_effect=_record):
        await writer.start()
        await writer.stop()

    tables = {t for t, _ in inserted}
    assert cfg.samples_table_id in tables
    assert cfg.summary_table_id in tables
    for table_id, rows in inserted:
        if table_id == cfg.summary_table_id:
            assert rows == [{"run_id": "r1", "status": "completed"}]
        else:
            assert rows == [{"run_id": "r1", "metric": "m"}]
