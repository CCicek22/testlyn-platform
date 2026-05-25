"""Orchestrator: read run metadata → render PDF → upload → notify API.

Entrypoint reads RUN_ID from env and calls run_report().
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import structlog

from report_builder.ai import summarize_run
from report_builder.pdf import PdfResult, build_pdf

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Config (read from env; safe defaults for local dev)
# ---------------------------------------------------------------------------

REPORTS_BUCKET = os.getenv("REPORTS_BUCKET", "testlyn-prod-reports")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------


async def run_report(
    run_id: str,
    *,
    org_id: str = "unknown",
    summary: dict[str, Any] | None = None,
    bq_client: Any | None = None,
    gcs_client: Any | None = None,
) -> PdfResult:
    """Full pipeline for one test run.

    1. Call AI summarizer (stub or real Gemini via API).
    2. Build and upload PDF.
    3. POST callback to API so the run record is updated with the report URI.

    Args:
        run_id: The test run UUID.
        org_id: Organisation identifier.
        summary: k6 summary dict (optional; pulled from BQ if not provided).
        bq_client: google.cloud.bigquery.Client (optional; omit in tests).
        gcs_client: google.cloud.storage.Client (optional; omit in tests).

    Returns:
        PdfResult with gcs_uri and page_count.
    """
    summary = summary or {}

    log.info("run_report.start", run_id=run_id, org_id=org_id)

    # Step 1: AI summary
    ai_text = await summarize_run(run_id=run_id, summary=summary)

    # Step 2: Build PDF
    result = await build_pdf(
        run_id=run_id,
        org_id=org_id,
        summary=summary,
        ai_summary=ai_text,
        dest_bucket=REPORTS_BUCKET,
        bq_client=bq_client,
        gcs_client=gcs_client,
    )

    # Step 3: Notify API
    await _notify_api(run_id=run_id, report_gcs_uri=result.gcs_uri)

    log.info("run_report.done", run_id=run_id, gcs_uri=result.gcs_uri)
    return result


async def _notify_api(*, run_id: str, report_gcs_uri: str) -> None:
    url = f"{API_BASE_URL}/v1/internal/runs/{run_id}/report-ready"
    payload = {"report_gcs_uri": report_gcs_uri}
    # Internal endpoints are gated by a shared secret (X-Internal-Token).
    headers = {"X-Internal-Token": os.getenv("INTERNAL_TOKEN", "")}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        log.info("run_report.callback_ok", run_id=run_id, status=resp.status_code)
    except Exception:
        # Non-fatal: the PDF is already uploaded; API can be reconciled later.
        log.exception("run_report.callback_failed", run_id=run_id, url=url)


# ---------------------------------------------------------------------------
# CLI entrypoint (python -m report_builder)
# ---------------------------------------------------------------------------


def main() -> None:
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        raise SystemExit("RUN_ID env var is required")

    org_id = os.environ.get("ORG_ID", "unknown")

    # In production the BQ / GCS clients are constructed here with
    # Workload Identity (no explicit credentials needed on Cloud Run).
    try:
        from google.cloud import bigquery  # noqa: I001
        from google.cloud import storage  # type: ignore[attr-defined]

        bq_client: Any = bigquery.Client()
        gcs_client: Any = storage.Client()
    except Exception:
        log.warning("run_report.no_gcp_clients", reason="credentials unavailable or not installed")
        bq_client = None
        gcs_client = None

    asyncio.run(run_report(run_id=run_id, org_id=org_id, bq_client=bq_client, gcs_client=gcs_client))


if __name__ == "__main__":
    main()
