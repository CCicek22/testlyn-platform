"""Schema-correctness guards for the load product's BigQuery SQL.

Review finding: the stream/backfill queries referenced nonexistent columns
``value`` and ``tags`` — samples_1s is PRE-AGGREGATED by the sidecar
(p50/p90/p95/p99, count, delta, rate_per_sec; see windows.py to_bq_row and
infra/terraform/modules/bigquery/main.tf). The queries silently failed
(logged + returned []) so the live chart and backfill were permanently empty.
"""

from __future__ import annotations

import re

import pytest

from testlyn_api.products.load import bq_queries

_SQLS = {
    "stream": bq_queries._STREAM_METRICS_SQL.format(project="p", dataset="d"),
    "samples": bq_queries._RUN_SAMPLES_SQL.format(
        project="p", dataset="d", max_rows=bq_queries.MAX_SAMPLE_ROWS
    ),
}


@pytest.mark.parametrize("sql", _SQLS.values(), ids=_SQLS.keys())
def test_no_nonexistent_columns(sql: str) -> None:
    """samples_1s has no `value` or `tags` column — querying them errors."""
    assert not re.search(r"\bvalue\b", sql), "raw `value` column does not exist"
    assert not re.search(r"\btags\b", sql), "`tags` column does not exist (tag_* + tag_extra)"
    assert "JSON_VALUE" not in sql
    assert "APPROX_QUANTILES" not in sql, "percentiles are pre-aggregated by the sidecar"


@pytest.mark.parametrize("sql", _SQLS.values(), ids=_SQLS.keys())
def test_uses_preaggregated_schema(sql: str) -> None:
    # p95 from the pre-aggregated trend column, scoped to http_req_duration
    assert "AVG(p95)" in sql
    assert "metric = 'http_req_duration'" in sql
    # error rate = SUM(delta)/SUM(count) over the http_req_failed rate metric,
    # NOT the expected_response tag (which never existed in this schema)
    assert "SAFE_DIVIDE(SUM(delta), SUM(count))" in sql
    assert "metric = 'http_req_failed'" in sql
    # vus gauge: delta carries the latest value per window
    assert "MAX(delta)" in sql
    assert "metric = 'vus'" in sql
    # parameterized run id + ordering preserved
    assert "@run_id" in sql
    assert "ORDER BY ts ASC" in sql


def test_stream_query_keeps_live_window_filters() -> None:
    sql = _SQLS["stream"]
    assert "INTERVAL 60 SECOND" in sql
    assert "CURRENT_DATE()" in sql


def test_samples_query_keeps_row_cap() -> None:
    sql = _SQLS["samples"]
    assert f"LIMIT {bq_queries.MAX_SAMPLE_ROWS}" in sql
    assert sql.index("ORDER BY ts ASC") < sql.index("LIMIT")
