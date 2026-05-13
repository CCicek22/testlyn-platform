"""Functional test report builder — stub.

Returns the same PdfResult shape as the load report builder.
Full implementation will render a Playwright test run summary with
pass/fail/healed counts and per-test timing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)


@dataclass
class PdfResult:
    gcs_uri: str
    page_count: int


async def build_functional_report(run_id: uuid.UUID | str) -> PdfResult:
    """Stub: generate a PDF report for a completed functional test run.

    TODO: integrate with report-builder service — render per-test pass/fail,
    healed selectors, screenshot thumbnails, and AI narrative.
    """
    run_id_str = str(run_id)
    gcs_uri = f"gs://testlyn-prod-reports/functional/{run_id_str}/report.pdf"

    log.info(
        "functional.report.stub",
        run_id=run_id_str,
        note="report generation not yet implemented",
    )

    return PdfResult(gcs_uri=gcs_uri, page_count=1)
