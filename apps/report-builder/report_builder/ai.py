"""AI summary stub. Real implementation calls Gemini 3.1 Flash-Lite via Vertex AI."""

from typing import Any

CANNED_SUMMARY = (
    "Run completed within thresholds. Median latency stable across the duration; "
    "p95 within target. No error-rate spikes observed. Replace this stub with a "
    "Vertex AI Gemini call once Workload Identity is provisioned for the report SA."
)


async def summarize_run(*, run_id: str, summary: dict[str, Any]) -> str:
    """Stub: returns canned text. Real impl will call Gemini 3.1 Flash-Lite.

    Production prompt skeleton (already drafted, not wired):
      system: "You are a senior load-test analyst. Be concise, dev-to-dev."
      user:   "Run {run_id} stats: {summary}. Identify the top bottleneck if any.
               Output 3 short paragraphs: what happened, what to look at, what to try next."
    """
    _ = (run_id, summary)
    return CANNED_SUMMARY
