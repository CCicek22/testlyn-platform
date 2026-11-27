# Configuration reference

Brackwater services read their settings from environment variables. Names use
the prefix of the service they belong to. Every setting has a default, and the
service refuses to start when a required value is missing or malformed.

## gate

`GATE_PORT` sets the listening port and defaults to `8080`. `GATE_LOG_LEVEL`
accepts `debug`, `info`, `warn` or `error`, and defaults to `info`.

`gate.db_pool_size` is the number of Postgres connections per instance. The
default is `40`. Values above `100` are rejected because the database would
refuse the extra connections.

`gate.request_timeout_ms` caps how long a request may run before it returns
`504`. The default is `30000`.

## spool

`SPOOL_LANE_DEFAULT` names the lane for jobs without an explicit priority. It
defaults to `standard`. Valid lanes are `standard`, `priority` and `bulk`.

`spool.max_attempts` controls how many times a job is retried before it is
parked in the dead-letter queue. The default is `7`.

`spool.visibility_timeout_s` is how long a claimed job stays hidden from other
workers. The default is `120`. Set it above the slowest expected job, or the
same job will run twice.

## relay

`relay.max_inflight` limits concurrent jobs per worker process. The default is
`16`. Raising it increases database load, so change it together with
`gate.db_pool_size`.

`relay.db_wait_ms` is not a setting. It is a metric exported by the workers,
and the value is used in the backlog runbook.

## Secrets

Secrets never appear in this reference. Store them in the secret store and
reference them by name, for example `LEDGER_PRIMARY_HOST`. Environment dumps in
support tickets must be redacted before they are shared.

## Validation at startup

Each service validates its settings before it binds the port. A value that does
not parse prints the setting name and the rejected value, except for secrets,
which print only the setting name. The process exits with status 78 so that the
orchestrator shows a configuration error rather than a crash loop.

## Changing a value

Change settings through the deployment manifest, not by editing a running
container. A rolling restart applies the new values one zone at a time. Check
the rollout status before you change a second setting, because two changes at
once make the cause of a regression hard to find.
