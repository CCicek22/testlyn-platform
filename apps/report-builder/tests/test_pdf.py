"""Tests for the WeasyPrint PDF pipeline.

BQ and GCS are fully mocked — no real cloud calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from report_builder.pdf import (
    PdfResult,
    _chart_error_rate,
    _chart_latency,
    _chart_vus,
    _count_pdf_pages,
    build_pdf,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WINDOWS = [
    {"t": i, "p50": 100 + i, "p95": 200 + i, "p99": 300 + i, "error_rate": 0.01, "vus": 50}
    for i in range(10)
]

SAMPLE_SUMMARY = {
    "http_reqs": 5000,
    "http_failed": 12,
    "vus_max": 100,
    "p50_ms": 120,
    "p95_ms": 280,
    "p99_ms": 450,
    "status": "completed",
}


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------


def test_chart_latency_returns_nonempty_b64():
    b64 = _chart_latency(SAMPLE_WINDOWS)
    assert len(b64) > 100
    # PNG magic bytes encode to "iVBORw0KGgo" in base64
    assert b64.startswith("iVBORw0KGgo")


def test_chart_error_rate_returns_nonempty_b64():
    b64 = _chart_error_rate(SAMPLE_WINDOWS)
    assert len(b64) > 100
    assert b64.startswith("iVBORw0KGgo")


def test_chart_vus_returns_nonempty_b64():
    b64 = _chart_vus(SAMPLE_WINDOWS)
    assert len(b64) > 100
    assert b64.startswith("iVBORw0KGgo")


def test_chart_latency_single_point():
    """Single-point window must not crash."""
    b64 = _chart_latency([{"t": 0, "p50": 50, "p95": 90, "p99": 120, "error_rate": 0, "vus": 5}])
    assert len(b64) > 50


# ---------------------------------------------------------------------------
# _count_pdf_pages
# ---------------------------------------------------------------------------


def test_count_pdf_pages_counts_page_objects_not_page_tree():
    """Each `/Type /Page` leaf counts; the `/Type /Pages` tree node must not.

    Also: markers are not reliably newline-delimited in real PDF output, so a
    space- or bracket-terminated marker must still count.
    """
    pdf = (
        b"1 0 obj << /Type /Pages /Count 3 >> endobj\n"
        b"2 0 obj << /Type /Page /Parent 1 0 R >> endobj\n"
        b"3 0 obj << /Type /Page/Parent 1 0 R >> endobj\n"
        b"4 0 obj <</Type/Page /Parent 1 0 R>> endobj\n"
    )
    assert _count_pdf_pages(pdf) == 3


def test_count_pdf_pages_floor_is_one():
    assert _count_pdf_pages(b"no markers here") == 1


# ---------------------------------------------------------------------------
# build_pdf — no BQ, no GCS (offline smoke test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_pdf_no_clients_returns_result():
    result = await build_pdf(
        run_id="run-abc-123",
        org_id="org-xyz",
        summary=SAMPLE_SUMMARY,
        ai_summary="Test AI summary. p95 within target. No spikes.",
        dest_bucket="testlyn-prod-reports",
        bq_client=None,
        gcs_client=None,
    )
    assert isinstance(result, PdfResult)
    assert result.gcs_uri == "gs://testlyn-prod-reports/org-xyz/run-abc-123.pdf"
    assert result.page_count >= 1


@pytest.mark.asyncio
async def test_build_pdf_produces_pdf_bytes():
    """Verify WeasyPrint actually emits PDF-formatted bytes (>0 bytes, starts with %PDF)."""
    from unittest.mock import patch

    captured: list[bytes] = []

    original_write_pdf = None

    # Patch at WeasyPrint level to capture bytes before "upload"
    import weasyprint

    original_write_pdf = weasyprint.HTML.write_pdf

    def capture_write_pdf(self, *args, **kwargs):
        pdf_bytes = original_write_pdf(self, *args, **kwargs)
        captured.append(pdf_bytes)
        return pdf_bytes

    with patch.object(weasyprint.HTML, "write_pdf", capture_write_pdf):
        await build_pdf(
            run_id="run-test-bytes",
            org_id="org-bytes",
            summary=SAMPLE_SUMMARY,
            ai_summary="Bytes check.",
            dest_bucket="testlyn-prod-reports",
            bq_client=None,
            gcs_client=None,
        )

    assert captured, "write_pdf was never called"
    pdf_bytes = captured[0]
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF"), f"Not a PDF: first 8 bytes = {pdf_bytes[:8]!r}"


# ---------------------------------------------------------------------------
# build_pdf — mock BQ rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_pdf_with_bq_rows():
    """BQ client is mocked to return SAMPLE_WINDOWS rows."""
    mock_bq = MagicMock()

    # Make each mock row behave like a dict when passed to dict()
    rows = []
    for w in SAMPLE_WINDOWS:
        row = MagicMock()
        row.__iter__ = MagicMock(return_value=iter(w.items()))
        row.keys = MagicMock(return_value=w.keys())
        rows.append(row)

    mock_job = MagicMock()
    mock_job.result.return_value = [
        type("Row", (), {**w, "items": lambda self, _w=w: _w.items()})()
        for w in SAMPLE_WINDOWS
    ]
    mock_bq.query.return_value = mock_job

    with patch("report_builder.pdf._query_bq", return_value=SAMPLE_WINDOWS):
        result = await build_pdf(
            run_id="run-bq-mock",
            org_id="org-bq",
            summary=SAMPLE_SUMMARY,
            ai_summary="BQ mock test.",
            dest_bucket="testlyn-prod-reports",
            bq_client=mock_bq,
            gcs_client=None,
        )

    assert result.gcs_uri == "gs://testlyn-prod-reports/org-bq/run-bq-mock.pdf"
    assert result.page_count >= 1


# ---------------------------------------------------------------------------
# build_pdf — mock GCS upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_pdf_uploads_to_gcs():
    mock_gcs = MagicMock()
    mock_blob = MagicMock()
    mock_gcs.bucket.return_value.blob.return_value = mock_blob

    result = await build_pdf(
        run_id="run-gcs-mock",
        org_id="org-gcs",
        summary=SAMPLE_SUMMARY,
        ai_summary="GCS upload test.",
        dest_bucket="testlyn-prod-reports",
        bq_client=None,
        gcs_client=mock_gcs,
    )

    mock_gcs.bucket.assert_called_once_with("testlyn-prod-reports")
    mock_gcs.bucket.return_value.blob.assert_called_once_with("org-gcs/run-gcs-mock.pdf")
    mock_blob.upload_from_string.assert_called_once()
    call_kwargs = mock_blob.upload_from_string.call_args
    assert call_kwargs.kwargs.get("content_type") == "application/pdf" or (
        len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "application/pdf"
    )
    assert result.gcs_uri == "gs://testlyn-prod-reports/org-gcs/run-gcs-mock.pdf"
