"""
PDF report builder hook for WCAG 2.2 accessibility audits.

Responsibility split:
- This module is called by the API to TRIGGER report generation.
- Actual PDF rendering is done by apps/report-builder/ (separate service),
  called via HTTP POST to its /render endpoint.
- The rendered PDF is uploaded to GCS bucket testlyn-prod-reports and the
  URI is stored in the run's summary_uri field.

The report-builder service applies the Testlyn brand (indigo #3730A3,
teal accent #14B8A6 for a11y, Inter font, dark surface) and emits a
structured WCAG 2.2 audit report with:
  - Executive summary (total / critical / serious / moderate / minor)
  - Per-violation section with impact badge, HTML snippet, dom_path,
    LLM-generated remediation text, and WCAG success criterion reference
  - Scan metadata (target URLs, axe-core version, scan timestamp)

TODO(W2C + report-builder stream):
  - Implement report-builder /render endpoint with WCAG 2.2 template.
  - Wire report_builder_url config setting in config.py.
  - Call trigger_pdf_report() from the a11y tasks.py completion handler.
"""

from __future__ import annotations

import structlog

from testlyn_api.products.a11y.schemas import A11yReport

log = structlog.get_logger(__name__)


async def trigger_pdf_report(report: A11yReport, *, org_id: str) -> str | None:
    """
    POST the violation report to the report-builder service and return the GCS URI.

    Returns None if report-builder is unreachable (non-fatal — PDF is best-effort).
    """
    from testlyn_api.config import get_settings

    settings = get_settings()
    report_builder_url = getattr(settings, "report_builder_url", None)

    if not report_builder_url:
        log.warning(
            "a11y.reports.no_builder_url",
            run_id=str(report.run_id),
            note="Set REPORT_BUILDER_URL to enable PDF generation.",
        )
        return None

    try:
        import httpx

        payload = {
            "product": "a11y",
            "run_id": str(report.run_id),
            "org_id": org_id,
            "summary": report.summary.model_dump(),
            "violations": [v.model_dump() for v in report.violations],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{report_builder_url}/render", json=payload)
            resp.raise_for_status()
            data = resp.json()
            gcs_uri: str = data["gcs_uri"]

        log.info(
            "a11y.reports.pdf_generated",
            run_id=str(report.run_id),
            gcs_uri=gcs_uri,
        )
        return gcs_uri

    except Exception as exc:
        log.warning(
            "a11y.reports.pdf_failed",
            run_id=str(report.run_id),
            error=str(exc),
        )
        return None
