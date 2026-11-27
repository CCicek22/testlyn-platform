# API notes: runs

Base path: `/v1/projects/{project_id}/runs`. All endpoints need a bearer token
for a principal with at least the `viewer` role in the project.

## Create a run

`POST /v1/projects/{project_id}/runs` starts a run. The request body names the
target, the profile and the scenario by id. The response is `202 Accepted` with
a `Location` header that points at the run resource. The run has not finished
when the response returns.

```json
{"target_id": "tgt_01", "profile": "smoke", "scenario": "hello-world"}
```

A request for a profile the project does not define returns `422` with the
code `PROFILE_UNKNOWN`. A request while the project already has the maximum
number of active runs returns `409` with the code `RUN_LIMIT_REACHED`.

## Read a run

`GET /v1/projects/{project_id}/runs/{run_id}` returns the state, the timestamps
and the summary once the run has finished. The state moves from `queued` to
`running` to `finished`, or to `aborted` when the run was stopped by a user or
by a threshold with the `abort_on_failure` option.

The summary includes the request count, the error count, and the latency
percentiles at p50, p90, p95 and p99. Percentiles are reported in milliseconds
as numbers with three decimal places.

## List runs

`GET /v1/projects/{project_id}/runs` pages with `limit` (default 50, maximum
200) and `cursor`. The cursor is opaque. Do not build one yourself, because the
format may change between releases.

## Stop a run

`POST /v1/projects/{project_id}/runs/{run_id}:stop` asks the run to finish. It
returns `202` immediately. The state changes to `aborted` after the workers
drain their in-flight requests, which takes up to 30 seconds.

## Errors

Error bodies have the shape `{"error": {"code": "...", "message": "..."}}`. The
message is for people and may change. Build client logic on the code only.

## Idempotency

Send an `Idempotency-Key` header with every create request. Retrying the same
key within 24 hours returns the original run instead of starting a second one.
A key reused with a different body returns `409` with the code
`IDEMPOTENCY_CONFLICT`. Keys are scoped to the project, so the same key in two
projects creates two runs.

## Pagination details

Cursors expire after one hour. A request with an expired cursor returns `410`
with the code `CURSOR_EXPIRED`, and the client should start again from the
first page. Lists are sorted by creation time, newest first, and runs created
during a traversal may or may not appear in later pages.
