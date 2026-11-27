# Incident note: gate timeouts during the March import

Status: closed. Severity: SEV-2. Owner: Lantern team.

## Summary

On a Tuesday in March, a customer import pushed about 40,000 jobs into the
`spool` queue within four minutes. `gate` requests began timing out at the
30 second limit, and the status page showed elevated errors for 47 minutes.
Run creation returned `504` with the code `GATE_UPSTREAM_TIMEOUT` for the
duration.

## Timeline

The import started at 09:12 UTC. The spool backlog alert fired at 09:17 UTC.
Engineers scaled the relay workers at 09:24 UTC, which cleared the queue by
09:51 UTC. The gate timeouts stopped at 09:59 UTC, once the connection pool
drained.

## Root cause

The `gate` service held a database connection while it waited for the spool
acknowledgement. Under load, the pool of 20 connections filled with requests
waiting on the queue, and new requests waited for a free connection. Health
checks still passed because they did not use the pool.

## What we changed

The acknowledgement wait now runs after the connection returns to the pool.
The pool size is configurable with `gate.db_pool_size`, and the default rose to
40. The health check now uses a pool connection, so a full pool shows up as an
unhealthy instance.

## Follow-ups

Import jobs now go to the `bulk` lane by default. The runbook for backlog
handling gained a step that checks the pool wait metric before scaling. The
team added the alert `GatePoolExhausted`, which fires when the wait exceeds 500
ms for five minutes.

## Lessons

A health check that skips the resource under stress is not a health check. Test
the alert path during the next import rehearsal, not only in staging.

## Customer impact

Eleven projects saw run creation fail during the window. Runs that were already
active continued normally, because their workers did not call `gate` while
running. The affected projects received a credit under the service level
terms, and the credit notes list the project ids and the minutes of impact.

## Detection

The first signal was not the status page. Support tickets reported failed run
creation about nine minutes before any alert fired. The gap is now a tracked
action: the synthetic run-create check runs every minute from two regions.
