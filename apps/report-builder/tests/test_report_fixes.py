"""Review-finding tests for the report-builder.

1. Dockerfile must ship templates/ into the runtime image — pdf.py resolves
   TEMPLATES_DIR = report_builder/../templates (= /app/templates); without the
   COPY every render raised TemplateNotFound.
2. _query_bq must derive every series' t from ONE run-wide baseline
   (MIN(window_start) over all metrics) — per-CTE baselines gave each series a
   different t=0 epoch, misaligning the PDF curves.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

from report_builder.pdf import TEMPLATES_DIR, _query_bq

APP_DIR = Path(__file__).resolve().parents[1]


def test_dockerfile_copies_templates() -> None:
    dockerfile = (APP_DIR / "Dockerfile").read_text()
    assert re.search(r"^COPY templates \./templates$", dockerfile, re.MULTILINE), (
        "Dockerfile must COPY templates ./templates or every render raises "
        "TemplateNotFound in the container"
    )


def test_templates_dir_matches_dockerfile_layout() -> None:
    # TEMPLATES_DIR is <app>/templates next to the report_builder package —
    # the same relative layout the Dockerfile produces under /app.
    assert TEMPLATES_DIR == APP_DIR / "templates"
    assert (TEMPLATES_DIR / "run_report.html").exists()


def _captured_query() -> str:
    captured: dict = {}

    def fake_query(query, job_config=None):  # type: ignore[no-untyped-def]
        captured["query"] = query
        job = MagicMock()
        job.result.return_value = []
        return job

    client = MagicMock()
    client.query.side_effect = fake_query
    _query_bq("run-1", client)
    return captured["query"]


def test_query_uses_single_runwide_baseline() -> None:
    query = _captured_query()
    # Exactly ONE MIN(window_start): the shared `base` CTE. Per-metric
    # baselines (the old MIN(...) OVER (PARTITION BY run_id) in each CTE)
    # misalign the series.
    assert query.count("MIN(window_start)") == 1
    assert "WITH base AS" in query
    assert "OVER (PARTITION BY run_id)" not in query
    # Every series joins the shared baseline.
    assert query.count("CROSS JOIN base b") == 3
    assert query.count("TIMESTAMP_DIFF(s.window_start, b.t0, SECOND)") == 3
