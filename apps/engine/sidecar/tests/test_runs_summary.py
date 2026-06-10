"""Tests for runs_summary row construction (spec §5 aggregate columns)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sidecar.bq_writer import BQWriter, _extract_summary_aggregates
from sidecar.config import SidecarConfig
from sidecar.spool import Spool


def _cfg(tmp_path: Path) -> SidecarConfig:
    return SidecarConfig(
        RUN_ID="r1",
        ORG_ID="o1",
        GCP_PROJECT="proj",
        SPOOL_DIR=str(tmp_path / "spool"),
    )


_K6_SUMMARY = {
    "metrics": {
        "vus_max": {"values": {"value": 42, "max": 50}},
        "iterations": {"values": {"count": 1234}},
        "http_reqs": {"values": {"count": 56789}},
        "http_req_failed": {"values": {"fails": 12, "passes": 56777}},
        "data_sent": {"values": {"count": 1_000_000}},
        "data_received": {"values": {"count": 9_000_000}},
    }
}


class TestExtract:
    def test_full_blob(self) -> None:
        out = _extract_summary_aggregates(_K6_SUMMARY)
        assert out == {
            "vus_max": 50,
            "iterations": 1234,
            "http_reqs": 56789,
            "http_failed": 12,
            "data_sent": 1_000_000,
            "data_received": 9_000_000,
        }

    def test_none_blob_returns_all_nulls(self) -> None:
        out = _extract_summary_aggregates(None)
        assert all(v is None for v in out.values())

    def test_missing_keys_become_null(self) -> None:
        out = _extract_summary_aggregates({"metrics": {"vus_max": {"values": {"value": 5}}}})
        assert out["vus_max"] == 5
        assert out["iterations"] is None
        assert out["http_reqs"] is None

    def test_malformed_values_become_null(self) -> None:
        out = _extract_summary_aggregates(
            {"metrics": {"vus_max": {"values": {"value": "not-an-int"}}}}
        )
        assert out["vus_max"] is None


class TestWriteRunsSummary:
    @pytest.mark.asyncio
    async def test_row_includes_spec_aggregates(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        spool = Spool(str(tmp_path / "spool"))
        writer = BQWriter(cfg, spool=spool)

        captured: list[list[dict[str, Any]]] = []

        async def fake_insert(rows: list[dict[str, Any]], *, table_id: str, kind: str = "samples_1s") -> None:
            captured.append(rows)

        with patch.object(writer, "_insert_with_retry", side_effect=fake_insert):
            await writer.write_runs_summary(
                started_at=datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC),
                finished_at=datetime(2026, 5, 16, 12, 0, 30, tzinfo=UTC),
                status="completed",
                summary_json=_K6_SUMMARY,
            )

        assert len(captured) == 1
        row = captured[0][0]
        assert row["status"] == "completed"
        assert row["vus_max"] == 50
        assert row["iterations"] == 1234
        assert row["http_reqs"] == 56789
        assert row["http_failed"] == 12
        assert row["data_sent"] == 1_000_000
        assert row["data_received"] == 9_000_000

    @pytest.mark.asyncio
    async def test_row_nulls_when_summary_missing(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        spool = Spool(str(tmp_path / "spool"))
        writer = BQWriter(cfg, spool=spool)

        captured: list[list[dict[str, Any]]] = []

        async def fake_insert(rows: list[dict[str, Any]], *, table_id: str, kind: str = "samples_1s") -> None:
            captured.append(rows)

        with patch.object(writer, "_insert_with_retry", side_effect=fake_insert):
            await writer.write_runs_summary(
                started_at=datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC),
                finished_at=datetime(2026, 5, 16, 12, 0, 30, tzinfo=UTC),
                status="failed",
                summary_json=None,
            )

        row = captured[0][0]
        assert row["status"] == "failed"
        for key in (
            "vus_max",
            "iterations",
            "http_reqs",
            "http_failed",
            "data_sent",
            "data_received",
        ):
            assert row[key] is None
