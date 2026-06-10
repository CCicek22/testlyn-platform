from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Module-level singleton — google.cloud.bigquery.Client opens an HTTP session
# and a credentials chain on construction; instantiating it on every SSE tick
# (once per second per viewer) is a measurable hot spot. Keyed by project so a
# project change in tests creates a fresh client.
_BQ_CLIENT: Any = None
_BQ_CLIENT_PROJECT: str | None = None


def _get_client(project: str) -> Any:
    """Return a process-wide bigquery.Client for ``project`` (lazy)."""
    global _BQ_CLIENT, _BQ_CLIENT_PROJECT
    if _BQ_CLIENT is not None and _BQ_CLIENT_PROJECT == project:
        return _BQ_CLIENT

    from google.cloud import bigquery

    _BQ_CLIENT = bigquery.Client(project=project)
    _BQ_CLIENT_PROJECT = project
    return _BQ_CLIENT

# samples_1s is PRE-AGGREGATED by the sidecar (see windows.py to_bq_row +
# infra/terraform/modules/bigquery/main.tf): one row per (metric, tag_bucket,
# 1s window) with p50/p90/p95/p99, count, delta, rate_per_sec — there is NO
# raw `value` or `tags` column. These queries mirror the report-builder's
# pdf.py _query_bq:
#   * p95 latency: AVG(p95) across tag buckets WHERE metric='http_req_duration'
#   * error rate: http_req_failed is a k6 'rate' metric — per row `count` is
#     total observations and `delta` is the failure count, so the volume-
#     weighted fraction is SAFE_DIVIDE(SUM(delta), SUM(count))
#   * vus: gauge metric — `delta` carries the latest value per window
_STREAM_METRICS_SQL = """
WITH latency AS (
  SELECT
    TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
    AVG(p95) AS p95_duration_ms
  FROM `{project}.{dataset}.samples_1s`
  WHERE run_id = @run_id
    AND metric = 'http_req_duration'
    AND DATE(window_start) = CURRENT_DATE()
    AND window_start >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 SECOND)
  GROUP BY ts
),
errors AS (
  SELECT
    TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
    SAFE_DIVIDE(SUM(delta), SUM(count)) AS error_rate
  FROM `{project}.{dataset}.samples_1s`
  WHERE run_id = @run_id
    AND metric = 'http_req_failed'
    AND DATE(window_start) = CURRENT_DATE()
    AND window_start >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 SECOND)
  GROUP BY ts
),
vus AS (
  SELECT
    TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
    MAX(delta) AS vus
  FROM `{project}.{dataset}.samples_1s`
  WHERE run_id = @run_id
    AND metric = 'vus'
    AND DATE(window_start) = CURRENT_DATE()
    AND window_start >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 SECOND)
  GROUP BY ts
)
SELECT
  l.ts,
  l.p95_duration_ms,
  COALESCE(e.error_rate, 0) AS error_rate,
  COALESCE(v.vus, 0) AS vus
FROM latency l
LEFT JOIN errors e ON l.ts = e.ts
LEFT JOIN vus v ON l.ts = v.ts
ORDER BY ts ASC
"""


# Hard cap on rows returned by the /samples endpoint: 86400 = 24h of 1s
# buckets. A multi-hour run could otherwise stream tens of thousands of rows.
# Capping to the FIRST N seconds (ORDER BY ts ASC + LIMIT) keeps the chart's
# leading window intact rather than truncating an arbitrary middle slice.
MAX_SAMPLE_ROWS = 86_400

_RUN_SAMPLES_SQL = """
WITH latency AS (
  SELECT
    TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
    AVG(p95) AS p95_duration_ms
  FROM `{project}.{dataset}.samples_1s`
  WHERE run_id = @run_id
    AND metric = 'http_req_duration'
  GROUP BY ts
),
errors AS (
  SELECT
    TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
    SAFE_DIVIDE(SUM(delta), SUM(count)) AS error_rate
  FROM `{project}.{dataset}.samples_1s`
  WHERE run_id = @run_id
    AND metric = 'http_req_failed'
  GROUP BY ts
),
vus AS (
  SELECT
    TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
    MAX(delta) AS vus
  FROM `{project}.{dataset}.samples_1s`
  WHERE run_id = @run_id
    AND metric = 'vus'
  GROUP BY ts
)
SELECT
  l.ts,
  l.p95_duration_ms,
  COALESCE(e.error_rate, 0) AS error_rate,
  COALESCE(v.vus, 0) AS vus
FROM latency l
LEFT JOIN errors e ON l.ts = e.ts
LEFT JOIN vus v ON l.ts = v.ts
ORDER BY ts ASC
LIMIT {max_rows}
"""


async def fetch_run_samples(
    *,
    run_id: uuid.UUID,
    project: str,
    dataset: str,
) -> list[dict[str, Any]]:
    """Return ALL persisted per-second samples_1s rows for ``run_id``, time-ordered.

    Same per-second aggregation + element shape as :func:`stream_run_metrics`
    (``ts``, ``p95_duration_ms``, ``error_rate``, ``vus``) but without the live
    60s/current-day window — used to back-fill the chart for a completed run.
    """
    try:
        from google.cloud import bigquery
    except ImportError:
        log.warning("bq_queries.bigquery_unavailable", run_id=str(run_id))
        return []

    client = _get_client(project)

    sql = _RUN_SAMPLES_SQL.format(project=project, dataset=dataset, max_rows=MAX_SAMPLE_ROWS)

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", str(run_id)),
        ]
    )

    try:
        query_job = await asyncio.to_thread(client.query, sql, job_config=job_config)
        rows = await asyncio.to_thread(query_job.result)
    except Exception as exc:
        log.error("bq_queries.samples_query_failed", run_id=str(run_id), error=str(exc))
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "ts": row.ts.isoformat() if row.ts else None,
                "p95_duration_ms": row.p95_duration_ms,
                "error_rate": float(row.error_rate) if row.error_rate is not None else 0.0,
                "vus": int(row.vus) if row.vus is not None else 0,
            }
        )

    return results


async def stream_run_metrics(
    *,
    run_id: uuid.UUID,
    project: str,
    dataset: str,
) -> list[dict[str, Any]]:
    """
    Query BigQuery for the last 60s of samples_1s for the given run.

    Returns list of dicts with keys: ts, p95_duration_ms, error_rate, vus.
    Each dict corresponds to a 1-second window.
    """
    try:
        from google.cloud import bigquery
    except ImportError:
        log.warning("bq_queries.bigquery_unavailable", run_id=str(run_id))
        return []

    client = _get_client(project)

    sql = _STREAM_METRICS_SQL.format(project=project, dataset=dataset)

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", str(run_id)),
        ]
    )

    try:
        query_job = await asyncio.to_thread(client.query, sql, job_config=job_config)
        rows = await asyncio.to_thread(query_job.result)
    except Exception as exc:
        log.error("bq_queries.query_failed", run_id=str(run_id), error=str(exc))
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "ts": row.ts.isoformat() if row.ts else None,
                "p95_duration_ms": row.p95_duration_ms,
                "error_rate": float(row.error_rate) if row.error_rate is not None else 0.0,
                "vus": int(row.vus) if row.vus is not None else 0,
            }
        )

    return results
