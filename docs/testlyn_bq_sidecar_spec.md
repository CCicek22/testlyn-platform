# Testlyn — BigQuery Sidecar Contract Spec
> Companion spec for **Phase 1, Deliverable #4** (k6 worker container)
> Status: authoritative · revise only with explicit decision log entry

## 1. Purpose

The BigQuery (BQ) sidecar is the second process in every k6 worker container. It exists for three reasons:

1. **License safety.** Stock `grafana/k6` is AGPLv3. The sidecar consumes k6's standard JSONL output via stdout/file — no linking, no derivative work. k6 remains an unmodified subprocess.
2. **Cost control.** Raw k6 sample volume is enormous (tens of millions of rows per 60-min test at 10k VUs). The sidecar pre-aggregates into 1-second tumbling windows before streaming to BQ, reducing row count by 100–1000× without losing chart fidelity.
3. **Reusability.** Every future Testlyn product that emits a JSON metric stream (security scans, contract tests, RUM) reuses this sidecar with a different parser plugin. Design it generic from day 1.

## 2. Non-goals

- Real-time dashboards (handled by Cloud Run API querying BQ — sidecar only writes)
- Long-term retention or archival (handled by BQ table partition expiration policy)
- Cross-test analytics (handled at API/reporting layer)
- Replacing k6's summary JSON (the summary is uploaded separately on completion by the entrypoint script)

## 3. Repository location

```
/apps/engine/
├── Dockerfile              # 2-stage: stock k6 + Python sidecar
├── entrypoint.sh           # orchestrates k6 + sidecar lifecycle
├── sidecar/
│   ├── __init__.py
│   ├── main.py             # CLI entry, env config, lifecycle
│   ├── parsers/
│   │   ├── base.py         # Parser protocol
│   │   └── k6.py           # k6 JSONL → SampleEvent
│   ├── windows.py          # tumbling-window aggregator + t-digest
│   ├── bq_writer.py        # batching + streaming inserts + retry
│   ├── spool.py            # /tmp spool for BQ-unavailable fallback
│   ├── health.py           # liveness/readiness for sidecar process
│   └── tests/
└── pyproject.toml
```

## 4. Input contract — k6 JSONL stream

The sidecar tails a JSONL file or named pipe (configurable; default `/tmp/k6.jsonl`). Each line is one JSON object. k6 emits two object types:

**Metric definition (one per metric, emitted once at start):**
```json
{
  "type": "Metric",
  "data": {
    "name": "http_req_duration",
    "type": "trend",
    "contains": "time",
    "thresholds": ["p(95)<500"],
    "submetrics": null
  },
  "metric": "http_req_duration"
}
```

**Point sample (one per metric event, emitted continuously):**
```json
{
  "type": "Point",
  "data": {
    "time": "2026-05-12T14:23:00.123Z",
    "value": 234.56,
    "tags": {
      "name": "https://api.example.com/users",
      "group": "::checkout",
      "method": "GET",
      "status": "200",
      "scenario": "default",
      "expected_response": "true"
    }
  },
  "metric": "http_req_duration"
}
```

**Always verify the current k6 JSON output format against `https://grafana.com/docs/k6/latest/results-output/real-time/json/` before implementing — k6 may add fields between versions.** Pin k6 to a specific tag in the Dockerfile and re-verify on tag bump.

## 5. Output schema — BigQuery

**Dataset:** `testlyn_metrics` (in the Example Co GCP project for Phase 1)

**Table 1: `samples_1s` (primary write target — windowed aggregates)**

```sql
CREATE TABLE testlyn_metrics.samples_1s (
  -- run context (injected by sidecar from env)
  run_id        STRING    NOT NULL,
  org_id        STRING    NOT NULL,
  product       STRING    NOT NULL,   -- 'load' in Phase 1; 'functional', 'a11y', etc. later
  region        STRING    NOT NULL,

  -- window
  window_start  TIMESTAMP NOT NULL,   -- start of the 1-second tumbling window
  metric        STRING    NOT NULL,   -- e.g. 'http_req_duration'
  metric_type   STRING    NOT NULL,   -- 'trend' | 'counter' | 'gauge' | 'rate'

  -- tag bucket (sidecar groups by these for aggregation; configurable per metric)
  tag_method    STRING,
  tag_status    STRING,
  tag_scenario  STRING,
  tag_group     STRING,
  tag_name      STRING,               -- URL or named request, normalized
  tag_extra     JSON,                 -- any tags beyond the indexed ones

  -- aggregates (trend metrics)
  count         INT64,
  sum_value     FLOAT64,
  min_value     FLOAT64,
  max_value     FLOAT64,
  p50           FLOAT64,
  p90           FLOAT64,
  p95           FLOAT64,
  p99           FLOAT64,

  -- aggregates (counter / gauge / rate)
  delta         FLOAT64,              -- sum-of-increments for counter; latest for gauge
  rate_per_sec  FLOAT64,              -- for rate metrics, the success rate in this window

  inserted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(window_start)
CLUSTER BY run_id, metric;
```

**Table 2: `runs_summary` (one row per run, written on completion)**

```sql
CREATE TABLE testlyn_metrics.runs_summary (
  run_id        STRING    NOT NULL,
  org_id        STRING    NOT NULL,
  product       STRING    NOT NULL,
  region        STRING    NOT NULL,
  started_at    TIMESTAMP NOT NULL,
  finished_at   TIMESTAMP NOT NULL,
  vus_max       INT64,
  iterations    INT64,
  http_reqs     INT64,
  http_failed   INT64,
  data_sent     INT64,
  data_received INT64,
  summary_json  JSON,                 -- full k6 --summary-export blob
  status        STRING NOT NULL       -- 'completed' | 'partial' | 'failed'
)
PARTITION BY DATE(started_at)
CLUSTER BY org_id, run_id;
```

Partition expiration: 90 days for `samples_1s`, 730 days for `runs_summary` (set via Terraform).

## 6. Aggregation algorithm

**Window:** tumbling 1-second windows aligned to UTC second boundaries (not test-relative). One window per (run_id, metric, tag_bucket).

**Tag bucket policy:** by default, group by `(method, status, scenario, group, name)`. Operators can override per metric via config — for example, a customer might want to group `http_req_duration` only by `(method, status)` and ignore URL for cardinality control.

**Trend metrics** (`http_req_duration`, `http_req_blocked`, `http_req_connecting`, `iteration_duration`, etc.):
- Maintain a **t-digest** per (metric, tag_bucket) for the active window
- On window close: emit `count`, `sum`, `min`, `max`, `p50`, `p90`, `p95`, `p99`
- Use `pytdigest` or `tdigest` Python library — compression parameter 100 (balances accuracy and memory; ±1% accuracy at p99 with bounded memory ~10KB per digest)

**Counter metrics** (`http_reqs`, `iterations`, `data_sent`, `data_received`):
- Accumulate `delta` (sum of increments) for the window
- On window close: emit `delta`

**Gauge metrics** (`vus`, `vus_max`):
- Track latest value seen in the window
- On window close: emit as `delta`

**Rate metrics** (`http_req_failed`, `checks`):
- Track success/total counts
- On window close: emit `rate_per_sec = success / window_duration`

**Active window set:** the sidecar holds at most 5 concurrent windows per (metric, tag_bucket) to tolerate slight clock skew between k6 and the sidecar. Older windows are flushed when a sample arrives for a newer window.

## 7. Batching & flush strategy

**Buffer:** in-memory list of BQ rows ready to insert. Bounded at 50,000 rows; if exceeded, force flush regardless of timer.

**Flush triggers (whichever fires first):**
- Buffer reaches `BATCH_SIZE` rows (default **5,000**)
- Time since last flush exceeds `FLUSH_INTERVAL_SECONDS` (default **5 seconds**)
- k6 process has exited and all windows are closed (final flush)
- Graceful shutdown signal (SIGTERM)

**BQ API:** use `google-cloud-bigquery` Python client's `insert_rows_json` method. Do NOT use the streaming buffer load job API for Phase 1 — `insert_rows_json` is simpler and acceptable up to ~10k rows/sec which exceeds our needs.

**Retry policy on transient failure** (network, 503, 429):
- Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s — give up after 6 attempts
- On final failure, **spool** the batch to `/tmp/spool/<timestamp>.jsonl` and continue
- On startup, drain any leftover spool files first

**Hard failure (4xx other than 429):**
- Log error with full response payload
- Mark batch as poison, write to `/tmp/spool/poison/` for offline inspection
- Continue processing — never drop the k6 stream

## 8. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| BQ rate limited (429) | client raises `TooManyRequests` | Exponential backoff, then spool |
| BQ unavailable (503, network) | request timeout or connection error | Spool batch, retry every 30s |
| Sidecar OOM | container killed | Cloud Run Job retries the entire run; mark as `partial` |
| Sidecar crashes mid-run | k6 keeps running but no metrics | Entrypoint detects sidecar PID gone, kills k6, marks run `failed` |
| k6 exits early (non-zero) | k6 process exit code != 0 | Flush all open windows, write `runs_summary` with `status='failed'`, upload k6 stderr to GCS |
| k6 hangs | no JSONL line for >60s while VUs should be active | Entrypoint timeout kills k6 + sidecar, marks run `failed` |
| Container shutdown (SIGTERM) | signal handler triggered | Flush all windows, drain buffer to BQ, persist remaining spool to GCS, exit cleanly within 30s |

**On container shutdown for any reason:** any unsent batches in `/tmp/spool/` are uploaded to `gs://testlyn-prod-spool/{run_id}/` so a later cleanup job can replay them. Set up a Cloud Scheduler job that runs a "spool replay" Cloud Run Job hourly.

## 9. Resource budget

Target sizing for a single Cloud Run Job container at 4 vCPU / 16 GB running 10,000 VUs:

| Component | CPU | Memory |
|---|---|---|
| k6 binary | 2.5–3 vCPU | 8–10 GB |
| Sidecar (steady state) | 0.3–0.5 vCPU | 200–500 MB |
| Sidecar (flush burst) | 1–1.5 vCPU spike | up to 800 MB during flush |
| Buffer | — | bounded at 50k rows × ~1 KB = 50 MB |
| Spool fallback | — | up to 1 GB on /tmp before alarming |

**Hard rule:** sidecar memory must stay under 1 GB even at 50k VUs. T-digest is the load-bearing choice here — it gives bounded memory regardless of sample count.

## 10. Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `RUN_ID` | required | Injected by Cloud Run Job invoker |
| `ORG_ID` | required | Injected |
| `PRODUCT` | `load` | Future: `functional`, `a11y`, etc. |
| `REGION` | `us-central1` | Injected |
| `GCP_PROJECT` | required | Example Co project ID for Phase 1 |
| `BQ_DATASET` | `testlyn_metrics` | |
| `BQ_SAMPLES_TABLE` | `samples_1s` | |
| `BQ_SUMMARY_TABLE` | `runs_summary` | |
| `K6_OUTPUT_PATH` | `/tmp/k6.jsonl` | Named pipe or regular file |
| `WINDOW_SECONDS` | `1` | Tumbling window size |
| `BATCH_SIZE` | `5000` | Rows per BQ insert |
| `FLUSH_INTERVAL_SECONDS` | `5` | Max time between flushes |
| `MAX_BUFFER_ROWS` | `50000` | Force-flush ceiling |
| `TAG_GROUPING_PROFILE` | `default` | Named profile for tag bucket policy |
| `SPOOL_DIR` | `/tmp/spool` | Local fallback path |
| `SPOOL_GCS_BUCKET` | `testlyn-prod-spool` | Container-shutdown spillover |
| `LOG_LEVEL` | `INFO` | |

All configuration via env — no config files. Secrets (none currently required for sidecar) go through Secret Manager + Workload Identity if added later.

## 11. Lifecycle (managed by entrypoint.sh)

```
1. Pull script from gs://testlyn-prod-scripts/{org_id}/{test_id}/script.js → /tmp/script.js
2. mkfifo /tmp/k6.jsonl                          # named pipe for streaming
3. python -m sidecar.main &                       # start sidecar, save PID
4. SIDECAR_PID=$!
5. k6 run --out json=/tmp/k6.jsonl \
          --tag run_id=$RUN_ID \
          --tag org_id=$ORG_ID \
          --vus $VUS --duration $DURATION \
          --summary-export /tmp/summary.json \
          /tmp/script.js
   K6_EXIT=$?
6. Wait for sidecar to finish draining (sidecar exits when k6 closes the pipe)
7. wait $SIDECAR_PID
8. gcloud storage cp /tmp/summary.json gs://testlyn-prod-results/{org_id}/{run_id}/
9. POST to API callback with run summary + status
10. Sidecar writes runs_summary row to BQ as its final action before exit
```

## 12. Testing requirements

**Unit tests:**
- T-digest percentile accuracy ±1% at p95, ±2% at p99 vs numpy reference on synthetic distributions
- Window aggregation correctness — replay a known fixture stream, assert window boundaries and counts
- Tag bucketing — given a tag set and a grouping profile, assert correct bucket key
- BQ writer batch boundary — assert flush fires at exact BATCH_SIZE and FLUSH_INTERVAL boundaries
- Retry logic — mock 503 responses, assert exponential backoff and eventual spool

**Integration tests:**
- Replay a 60-second 100-VU fixture k6 run end-to-end, assert BQ row count and metric coverage
- Inject a BQ outage mid-run (mock client raises 503 for 60s), assert spool + recovery
- Force sidecar SIGTERM mid-flush, assert graceful drain within 30s

**Load tests** (run in CI nightly):
- Replay a 10-minute 10,000-VU fixture (pre-recorded JSONL file), assert:
  - Sidecar memory stays under 800 MB peak
  - Zero data loss (rows in BQ == expected window count × metric count × tag bucket count)
  - p99 batch flush latency under 2 seconds

## 13. Reference skeleton (Python — for orientation only, not full implementation)

```python
# apps/engine/sidecar/main.py
import asyncio, os, signal, logging
from sidecar.parsers.k6 import K6Parser
from sidecar.windows import WindowAggregator
from sidecar.bq_writer import BQWriter
from sidecar.spool import Spool

async def main():
    cfg = load_config_from_env()
    parser = K6Parser(cfg.k6_output_path)
    aggregator = WindowAggregator(window_seconds=cfg.window_seconds)
    spool = Spool(cfg.spool_dir, cfg.spool_gcs_bucket)
    writer = BQWriter(cfg, spool=spool)

    await spool.drain_existing()  # any leftover from previous run

    install_signal_handlers(parser, aggregator, writer)

    async for sample in parser.stream():
        closed_windows = aggregator.add(sample)
        for window in closed_windows:
            await writer.enqueue(window.to_bq_row(cfg.run_context))

    # k6 closed the pipe — drain remaining windows
    for window in aggregator.flush_all():
        await writer.enqueue(window.to_bq_row(cfg.run_context))

    await writer.final_flush()
    await writer.write_runs_summary(cfg.run_context)

if __name__ == "__main__":
    asyncio.run(main())
```

## 14. Observability

The sidecar itself must emit structured logs to stdout (JSON format, picked up automatically by Cloud Logging). Required log events:

- `sidecar.started` — once on startup with full config
- `sidecar.window_emitted` — DEBUG level only, includes metric and bucket
- `sidecar.batch_flushed` — INFO, includes row count and latency
- `sidecar.batch_failed` — WARN, includes retry attempt and error
- `sidecar.spooled` — WARN with batch size and reason
- `sidecar.spool_drained` — INFO with row count
- `sidecar.shutdown` — INFO with final stats (total rows, total batches, total spool incidents)

Cloud Monitoring custom metrics (set up via Terraform):

- `testlyn/sidecar/rows_sent_total` (counter, labels: run_id, status=success|spooled|poison)
- `testlyn/sidecar/batch_flush_latency_ms` (distribution)
- `testlyn/sidecar/buffer_size` (gauge)
- `testlyn/sidecar/spool_size_bytes` (gauge)

Alert on: `spool_size_bytes > 100 MB for 5 min` → indicates sustained BQ outage; page on-call.

## 15. Versioning + change control

This spec is versioned with the engine container. Bump `SIDECAR_SPEC_VERSION` in `pyproject.toml` and add a changelog entry in `apps/engine/CHANGELOG.md` for any:

- Schema change to `samples_1s` or `runs_summary` (also requires BQ migration)
- New metric type support
- Change to default `WINDOW_SECONDS`, `BATCH_SIZE`, or `FLUSH_INTERVAL_SECONDS`
- New env var or removal of existing one

Schema changes require both a new table version (e.g. `samples_1s_v2`) AND a backfill plan. Never break-change an existing partition.

---

*End of spec v1. Update only with explicit decision log entry.*
