"""PDF builder stub. Real implementation uses WeasyPrint + Matplotlib (Phase 1 follow-up)."""

from dataclasses import dataclass
from typing import Any


@dataclass
class PdfResult:
    gcs_uri: str
    page_count: int


async def build_pdf(*, run_id: str, summary: dict[str, Any], dest_bucket: str) -> PdfResult:
    """Stub: returns a fake GCS URI without producing any bytes.

    The real implementation will:
      1. Query BigQuery `samples_1s` for the run's aggregated metrics.
      2. Render Matplotlib charts (latency over time, error rate, VU count).
      3. Compose a WeasyPrint HTML template with Testlyn branding.
      4. Upload the PDF to `gs://{dest_bucket}/{run_id}.pdf`.
      5. Return a signed URL via the API layer.
    """
    return PdfResult(gcs_uri=f"gs://{dest_bucket}/{run_id}.pdf", page_count=0)
