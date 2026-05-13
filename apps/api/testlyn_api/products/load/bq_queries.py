from __future__ import annotations

import uuid
from typing import Any

import structlog

log = structlog.get_logger(__name__)

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

    client = bigquery.Client(project=project)

    sql = _STREAM_METRICS_SQL.format(project=project, dataset=dataset)

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", str(run_id)),
        ]
    )

    try:
        query_job = client.query(sql, job_config=job_config)
        rows = query_job.result()
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
