# Runbook: spool backlog

Owner: Lantern team. Applies to the Brackwater `spool` service, which queues
jobs between the `gate` API and the `relay` workers.

## Symptoms

The `SpoolBacklogHigh` alert fires when more than 5000 jobs sit in the queue
for 10 minutes. Users see run start times slide by minutes instead of seconds.
The dashboard panel "Queued jobs" climbs in a sawtooth pattern when workers
restart.

## First checks

Start with the queue summary. The command below prints depth per priority lane,
the oldest job age, and the number of live consumers.

```sh
brackctl spool stats --lane all --format table
```

Next, compare producer and consumer rates. A consumer that falls behind the
producers is the usual cause of a growing queue. Consumers that are healthy
but slow usually point at the database, so check the `relay.db_wait_ms`
histogram before scaling anything.

Jobs that fail repeatedly move to the dead-letter queue `spool-dlq`. After
seven failed attempts a job is parked there. A dead-letter count that rises
together with the backlog means the workers are crashing, not just slow.

## Mitigation

Scale consumers first. Scaling is safe while the database wait stays under
40 ms at p95.

```sh
brackctl spool scale --workers 12 --lane standard
```

Pause new low-priority submissions only when scaling does not clear the backlog
within 20 minutes. Use the `gate` feature flag `intake.low_priority` and record
the time in the incident channel.

Do not purge the queue. Purging drops jobs that users are waiting for, and the
purge command is not reversible. If a poisoned job blocks a lane, move that one
job to `spool-dlq` with `brackctl spool park <job-id>` and keep the rest.

## Recovery

When the depth returns below 500, scale the workers back down one step per
15 minutes. Re-enable the paused intake lane and confirm that the oldest job
age stays under 60 seconds for one full hour.

## Escalation

Page the platform on-call if the backlog is still growing after two scaling
steps, or if the dead-letter queue gains more than 200 jobs in an hour. The
on-call engineer should open an incident note using the template in the
incident folder.

## Notes

The lane names are `standard`, `priority` and `bulk`. Bulk jobs are the first
to be parked during a backlog because their runs have no interactive user.
