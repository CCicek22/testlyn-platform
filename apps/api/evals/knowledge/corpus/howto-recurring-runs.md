# How to schedule recurring runs

A recurring run starts a saved profile against a target on a fixed schedule.
Use one to catch slow regressions, for example a nightly ramp against staging.

## Creating a schedule

Open the project, choose Schedules, then New schedule. Pick the target, the
profile and the scenario, then set the cadence. The cadence accepts a cron
expression in UTC, such as `15 2 * * *` for 02:15 UTC every day.

Schedules run in UTC. When you read the dashboard in local time, convert the
hour yourself, because a schedule set to 09:00 runs at 09:00 UTC regardless of
the browser's time zone.

## Concurrency

Each project can run at most three scheduled runs at once. A schedule that
would start while three runs are active is skipped, and the skip appears in
the schedule history with the reason `concurrency-limit`.

Skipped runs are not retried. If a regression check must run every night, keep
the other schedules in the project short, or ask an admin to raise the limit.

## Failed runs

A scheduled run that fails to start is retried three times, five minutes apart.
After the third failure the schedule is marked `needs-attention` and an email
goes to the schedule owner. A run that starts but finishes with threshold
failures is not retried, because the result is a real measurement.

## Pausing and deleting

Pausing a schedule keeps its history and configuration. Deleting it removes the
history after 30 days, so export the reports you need before you delete.

## Comparing scheduled runs

The schedule page plots p95 latency and error rate for the last 30 scheduled
runs. Each point links to its report. A single slow night is often noise, so
look for a change that lasts three or more consecutive runs before you
investigate.

To compare two runs directly, open both reports and use Compare. The compare
view aligns the latency histograms and marks any percentile that moved by more
than 15 percent in either direction. Runs must use the same profile to be
compared, because the compare view refuses mixed profiles with the message
`profile-mismatch`.

## Notifications

A schedule can notify a channel when a run finishes with threshold failures.
Add a webhook under Notifications and select the schedule. The payload contains
the run id, the failed thresholds and the link to the report. It does not
contain request bodies or response headers, so nothing sensitive leaves the
platform through this path.

## Maintenance windows

A maintenance window stops every schedule in a project between two times in
UTC. Runs that would start inside the window are skipped with the reason
`maintenance-window`. Use a window when a staging deploy is planned, so that a
scheduled ramp does not measure a half-finished release.
