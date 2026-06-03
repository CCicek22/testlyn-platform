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

_STREAM_METRICS_SQL = """
SELECT
  TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
  APPROX_QUANTILES(
    CASE WHEN metric = 'http_req_duration' THEN value END,
    100
  )[OFFSET(95)] AS p95_duration_ms,
  SAFE_DIVIDE(
    COUNTIF(metric = 'http_reqs' AND JSON_VALUE(tags, '$.expected_response') = 'false'),
    NULLIF(COUNTIF(metric = 'http_reqs'), 0)
  ) AS error_rate,
  MAX(CASE WHEN metric = 'vus' THEN value END) AS vus
FROM `{project}.{dataset}.samples_1s`
WHERE
  run_id = @run_id
  AND DATE(window_start) = CURRENT_DATE()
  AND window_start >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 SECOND)
GROUP BY ts
ORDER BY ts ASC
"""


_RUN_SAMPLES_SQL = """
SELECT
  TIMESTAMP_TRUNC(window_start, SECOND) AS ts,
  APPROX_QUANTILES(
    CASE WHEN metric = 'http_req_duration' THEN value END,
    100
  )[OFFSET(95)] AS p95_duration_ms,
  SAFE_DIVIDE(
    COUNTIF(metric = 'http_reqs' AND JSON_VALUE(tags, '$.expected_response') = 'false'),
    NULLIF(COUNTIF(metric = 'http_reqs'), 0)
  ) AS error_rate,
  MAX(CASE WHEN metric = 'vus' THEN value END) AS vus
FROM `{project}.{dataset}.samples_1s`
WHERE run_id = @run_id
GROUP BY ts
ORDER BY ts ASC
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

    sql = _RUN_SAMPLES_SQL.format(project=project, dataset=dataset)

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
