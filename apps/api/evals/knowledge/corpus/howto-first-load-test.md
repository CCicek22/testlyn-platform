# How to run your first load test

This guide walks through a first Brackwater load test against a staging API.
It takes about fifteen minutes. You need a project, a target URL and the
`runner` role in the project.

## 1. Create a target

A target is the base URL plus the request budget you allow. Open the project,
choose Targets, then New target. Enter `https://staging.example.com` and keep
the default budget of 200 requests per second. Raise the budget only after a
first run has passed.

Targets can also be created from the command line:

```sh
brackctl target create --project orchid --url https://staging.example.com --budget-rps 200
```

## 2. Pick a profile

A profile describes how many virtual users to run and how long to hold them.
The `smoke` profile uses 5 users for 60 seconds. It is the right choice for a
first run because it finds broken routes without loading the staging database.

The `ramp` profile increases users in steps of 10 every 30 seconds until it
reaches the ceiling you set. Use it when you want to find the knee of the
latency curve.

## 3. Start the run

Start the run from the target page or with the CLI. A run needs a scenario,
which is covered in the scenario guide. For a first run, use the default
scenario named `hello-world`.

```sh
brackctl run start --target <target-id> --profile smoke --scenario hello-world
```

The command prints a run id. Watch the run page for the live p95 latency and
the error rate. The run stops on its own when the profile ends.

## 4. Read the summary

The summary has three parts: throughput, latency percentiles, and errors. The
error table groups failures by status code. A 429 means the request budget was
hit. A 503 means the target itself struggled.

Do not compare a smoke run with a ramp run. They measure different things, and
the averages are not comparable.

## 5. Next steps

Once the smoke run passes with zero unexpected errors, write a scenario that
matches a real user flow. Then run a ramp profile against the same target and
keep the results. Repeat runs on the same day are easier to compare than runs
spread across weeks.
