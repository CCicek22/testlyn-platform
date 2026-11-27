# How to write a scenario script

A scenario is a short JavaScript file that describes one user flow. Brackwater
runs the scenario once per virtual user. The file lives in the project's
`scenarios` folder and is stored in the knowledge base as text, so keep it
readable.

## Skeleton

Every scenario exports a single `flow` function. Its only argument is the
context object provided by the runner.

```js
export function flow(ctx) {
  const session = ctx.http.post("/v1/sessions", { user: ctx.vars.user });
  ctx.check(session, { "session created": (r) => r.status === 201 });
  ctx.http.get("/v1/orders?limit=20", { token: session.json("token") });
}
```

The runner records each request as one sample. Checks are not failures unless
they are declared as thresholds in the profile, so a failing check shows up in
the report without stopping the run.

## Data

Use `ctx.vars` for values loaded from a data file. Data files are CSV and are
read once per run, not once per request. Large data files slow the start of a
run, so keep them under 50 MB.

Never put real customer data in a scenario. The platform stores scenario text
without encryption at rest beyond the default disk encryption.

## Think time

Real users pause between actions. Add `ctx.sleep(seconds)` between groups of
requests. A scenario with no pauses measures the server at a rate no person
produces, which is useful for stress but misleading for capacity planning.

## Limits

A scenario may make at most 40 requests per iteration. Scripts that exceed the
limit fail validation when saved. Loops over unbounded lists are rejected for
the same reason.

## Testing a scenario

Run it once with the `dry` profile before any real run. The dry profile runs
one user for one iteration and prints every request and response status. It
does not send traffic to the budget.
