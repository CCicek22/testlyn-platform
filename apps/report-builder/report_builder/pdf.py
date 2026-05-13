"""WeasyPrint PDF pipeline for Testlyn run reports."""

from __future__ import annotations

import base64
import io
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import structlog
from jinja2 import Environment, FileSystemLoader

matplotlib.use("Agg")

log = structlog.get_logger(__name__)

# Testlyn theme constants
INDIGO = "#3730A3"
SUCCESS = "#10B981"
WARN = "#F59E0B"
ALERT = "#EF4444"
DARK_SURFACE = "#0A0A0B"
FONT_MONO = "monospace"

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@dataclass
class PdfResult:
    gcs_uri: str
    page_count: int


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------


def _apply_theme(ax: Any) -> None:
    ax.set_facecolor("#111113")
    ax.figure.set_facecolor("#111113")
    ax.tick_params(colors="#9CA3AF", labelsize=9, labelcolor="#9CA3AF")
    ax.xaxis.label.set_color("#9CA3AF")
    ax.yaxis.label.set_color("#9CA3AF")
    ax.title.set_color("#F9FAFB")
    ax.title.set_fontsize(11)
    for spine in ax.spines.values():
        spine.set_color("#374151")
    ax.grid(color="#1F2937", linestyle="--", linewidth=0.6)


def _fig_to_b64(fig: Any) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()


def _chart_latency(
    windows: list[dict[str, Any]],
) -> str:
    """Render p50/p95/p99 latency over time. Returns base64 PNG."""
    ts = [w["t"] for w in windows]
    p50 = [w.get("p50", 0) for w in windows]
    p95 = [w.get("p95", 0) for w in windows]
    p99 = [w.get("p99", 0) for w in windows]

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(ts, p50, color=INDIGO, linewidth=1.5, label="p50")
    ax.plot(ts, p95, color=WARN, linewidth=1.5, label="p95")
    ax.plot(ts, p99, color=ALERT, linewidth=1.5, label="p99")
    ax.set_xlabel("seconds into run", fontfamily=FONT_MONO)
    ax.set_ylabel("ms", fontfamily=FONT_MONO)
    ax.set_title("Latency over time (ms)")
    ax.legend(fontsize=9, labelcolor="#9CA3AF", facecolor="#1F2937", edgecolor="#374151")
    _apply_theme(ax)
    return _fig_to_b64(fig)


def _chart_error_rate(windows: list[dict[str, Any]]) -> str:
    """Render error-rate % over time. Returns base64 PNG."""
    ts = [w["t"] for w in windows]
    err = [w.get("error_rate", 0) * 100 for w in windows]

    fig, ax = plt.subplots(figsize=(8, 2.5))
    ax.fill_between(ts, err, color=ALERT, alpha=0.3)
    ax.plot(ts, err, color=ALERT, linewidth=1.2, label="error %")
    ax.set_xlabel("seconds into run", fontfamily=FONT_MONO)
    ax.set_ylabel("%", fontfamily=FONT_MONO)
    ax.set_title("Error rate (%)")
    ax.set_ylim(bottom=0)
    _apply_theme(ax)
    return _fig_to_b64(fig)


def _chart_vus(windows: list[dict[str, Any]]) -> str:
    """Render VU count over time. Returns base64 PNG."""
    ts = [w["t"] for w in windows]
    vus = [w.get("vus", 0) for w in windows]

    fig, ax = plt.subplots(figsize=(8, 2.5))
    ax.fill_between(ts, vus, color=SUCCESS, alpha=0.25)
    ax.plot(ts, vus, color=SUCCESS, linewidth=1.2)
    ax.set_xlabel("seconds into run", fontfamily=FONT_MONO)
    ax.set_ylabel("VUs", fontfamily=FONT_MONO)
    ax.set_title("Virtual users over time")
    ax.set_ylim(bottom=0)
    _apply_theme(ax)
    return _fig_to_b64(fig)


# ---------------------------------------------------------------------------
# BQ query helper
# ---------------------------------------------------------------------------


def _query_bq(run_id: str, bq_client: Any) -> list[dict[str, Any]]:
    """Pull per-second aggregates for a run from `samples_1s`.

    Returns a list of dicts ordered by elapsed second with keys:
      t, p50, p95, p99, error_rate, vus
    """
    query = """
        WITH latency AS (
            SELECT
                TIMESTAMP_DIFF(window_start,
                    MIN(window_start) OVER (PARTITION BY run_id),
                    SECOND) AS t,
                AVG(p50) AS p50,
                AVG(p95) AS p95,
                AVG(p99) AS p99
            FROM `testlyn_metrics.samples_1s`
            WHERE run_id = @run_id
              AND metric = 'http_req_duration'
            GROUP BY run_id, window_start
        ),
        errors AS (
            SELECT
                TIMESTAMP_DIFF(window_start,
                    MIN(window_start) OVER (PARTITION BY run_id),
                    SECOND) AS t,
                AVG(rate_per_sec) AS error_rate
            FROM `testlyn_metrics.samples_1s`
            WHERE run_id = @run_id
              AND metric = 'http_req_failed'
            GROUP BY run_id, window_start
        ),
        vus AS (
            SELECT
                TIMESTAMP_DIFF(window_start,
                    MIN(window_start) OVER (PARTITION BY run_id),
                    SECOND) AS t,
                AVG(delta) AS vus
            FROM `testlyn_metrics.samples_1s`
            WHERE run_id = @run_id
              AND metric = 'vus'
            GROUP BY run_id, window_start
        )
        SELECT
            l.t,
            l.p50,
            l.p95,
            l.p99,
            COALESCE(e.error_rate, 0) AS error_rate,
            COALESCE(v.vus, 0) AS vus
        FROM latency l
        LEFT JOIN errors e ON l.t = e.t
        LEFT JOIN vus v ON l.t = v.t
        ORDER BY l.t
    """
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    job_config = QueryJobConfig(
        query_parameters=[ScalarQueryParameter("run_id", "STRING", run_id)]
    )
    rows = list(bq_client.query(query, job_config=job_config).result())
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# HTML render
# ---------------------------------------------------------------------------


def _render_html(
    *,
    run_id: str,
    org_id: str,
    summary: dict[str, Any],
    ai_summary: str,
    chart_latency_b64: str,
    chart_error_b64: str,
    chart_vus_b64: str,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    tpl = env.get_template("run_report.html")
    return tpl.render(
        run_id=run_id,
        org_id=org_id,
        summary=summary,
        ai_summary=ai_summary,
        chart_latency=chart_latency_b64,
        chart_error=chart_error_b64,
        chart_vus=chart_vus_b64,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def build_pdf(
    *,
    run_id: str,
    org_id: str = "unknown",
    summary: dict[str, Any],
    ai_summary: str = "",
    dest_bucket: str,
    bq_client: Any | None = None,
    gcs_client: Any | None = None,
) -> PdfResult:
    """Render a WeasyPrint PDF for a completed test run and upload to GCS.

    Args:
        run_id: The test run UUID.
        org_id: Organisation identifier (used for GCS path prefix).
        summary: k6 summary-export dict (or equivalent aggregates).
        ai_summary: Pre-rendered AI paragraph (call ai.summarize_run first).
        dest_bucket: GCS bucket name, e.g. "testlyn-prod-reports".
        bq_client: Optional google.cloud.bigquery.Client. If None, BQ query
                   is skipped and charts are rendered with empty series.
        gcs_client: Optional google.cloud.storage.Client. If None, GCS upload
                    is skipped and the gcs_uri is returned as a placeholder.

    Returns:
        PdfResult with the GCS URI and rendered page count.
    """
    from weasyprint import HTML

    log.info("build_pdf.start", run_id=run_id, org_id=org_id)

    # 1. Fetch BQ metric series (empty fallback when no client)
    windows: list[dict[str, Any]] = []
    if bq_client is not None:
        try:
            windows = _query_bq(run_id, bq_client)
            log.info("build_pdf.bq_rows", count=len(windows))
        except Exception:
            log.exception("build_pdf.bq_query_failed", run_id=run_id)

    # Synthetic 1-point series so charts always have something to render
    if not windows:
        windows = [{"t": 0, "p50": 0, "p95": 0, "p99": 0, "error_rate": 0, "vus": 0}]

    # 2. Render charts
    chart_latency_b64 = _chart_latency(windows)
    chart_error_b64 = _chart_error_rate(windows)
    chart_vus_b64 = _chart_vus(windows)

    # 3. Render HTML
    html_str = _render_html(
        run_id=run_id,
        org_id=org_id,
        summary=summary,
        ai_summary=ai_summary or "AI summary not available.",
        chart_latency_b64=chart_latency_b64,
        chart_error_b64=chart_error_b64,
        chart_vus_b64=chart_vus_b64,
    )

    # 4. WeasyPrint → PDF bytes
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "report.html"
        html_path.write_text(html_str, encoding="utf-8")
        wp = HTML(filename=str(html_path))
        pdf_bytes = wp.write_pdf()

    page_count = _count_pdf_pages(pdf_bytes)
    log.info("build_pdf.rendered", run_id=run_id, bytes=len(pdf_bytes), pages=page_count)

    # 5. Upload to GCS
    gcs_path = f"{org_id}/{run_id}.pdf"
    gcs_uri = f"gs://{dest_bucket}/{gcs_path}"

    if gcs_client is not None:
        try:
            bucket = gcs_client.bucket(dest_bucket)
            blob = bucket.blob(gcs_path)
            blob.upload_from_string(pdf_bytes, content_type="application/pdf")
            log.info("build_pdf.uploaded", gcs_uri=gcs_uri)
        except Exception:
            log.exception("build_pdf.gcs_upload_failed", gcs_uri=gcs_uri)

    return PdfResult(gcs_uri=gcs_uri, page_count=page_count)


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count PDF pages by scanning for page object markers."""
    count = pdf_bytes.count(b"/Type /Page\n") + pdf_bytes.count(b"/Type/Page\n")
    return max(count, 1)
