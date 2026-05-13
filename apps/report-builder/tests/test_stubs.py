"""Smoke tests for the report-builder. Updated from stub to real pipeline."""

import pytest
from report_builder import build_pdf, summarize_run


@pytest.mark.asyncio
async def test_build_pdf_returns_uri():
    result = await build_pdf(
        run_id="abc-123",
        org_id="unknown",
        summary={},
        dest_bucket="testlyn-prod-reports",
    )
    assert result.gcs_uri == "gs://testlyn-prod-reports/unknown/abc-123.pdf"
    assert result.page_count >= 1


@pytest.mark.asyncio
async def test_summarize_run_returns_canned_text():
    text = await summarize_run(run_id="abc-123", summary={"total_requests": 1234})
    assert "Run completed" in text
    assert len(text) > 50
