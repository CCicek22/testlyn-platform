# Runbook: database failover

Owner: Marrow team. Covers the `ledger` Postgres cluster that stores run
metadata and org settings.

## When to fail over

Fail over only when the primary fails its health probe three times in a row
and the replica lag is below 5 seconds. A replica that lags more than that
would lose the most recent writes, so the decision needs the incident lead.

The health probe runs every 10 seconds against `ledger-primary:5432`. Its
result appears on the status page as `ledger-primary: degraded`.

## Procedure

1. Freeze writes at the `gate` layer with the flag `ledger.read_only`. Reads
   keep working, so users can still open their dashboards.
2. Confirm the replica position with `brackctl ledger replica-status`.
3. Promote the replica:

```sh
brackctl ledger promote --target ledger-replica-b --confirm
```

4. Point `gate` at the new primary by updating the secret
   `LEDGER_PRIMARY_HOST` in the secret store. Restart the gate pods one zone at
   a time.
5. Clear the read-only flag and watch the write error rate for 15 minutes.

The old primary must stay offline until someone has checked its timeline. It
must not rejoin the cluster as a primary on its own.

## Connection pooling

All applications connect through the PgBouncer pool at `ledger-pool:6432`. The pooler
keeps server connections warm, so a failover needs no client restart when the
pooler target is updated. Direct connections to port 5432 skip the pooler and
are not allowed from application code.

## Verification

After promotion, run the smoke check. It creates one test run in a throwaway
org, reads it back, and deletes it.

```sh
brackctl smoke run --org smoke-canary
```

A passing check prints `smoke: ok` and the elapsed time. A failing check
prints the failing step name, which tells you whether writes, reads or cleanup
broke.

## After the incident

Write the timeline in the incident note. Record the replica lag at the moment
of promotion, because it sets the window of possibly lost writes. Ask the
data owner to check runs created in that window.
