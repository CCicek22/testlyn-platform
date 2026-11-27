# API notes: rate limits

Brackwater limits API calls per principal, not per IP address. Limits apply to
the API and not to the load generator, which has its own request budget on each
target.

## Default limits

A personal token may make 60 requests per minute to read endpoints and 10 per
minute to write endpoints. A service account token has 300 and 60. Both limits
use a sliding window of 60 seconds.

Responses include three headers: `RateLimit-Limit`, `RateLimit-Remaining` and
`RateLimit-Reset`. The reset value is the number of seconds until the window
frees one request.

## Exceeding the limit

A request over the limit returns `429 Too Many Requests` with the code
`RATE_LIMITED` and a `Retry-After` header in seconds. Clients should wait for
that many seconds, then retry with jitter. Retrying immediately makes the
window stay full.

A burst is allowed up to the limit at once, so a script that starts with a
hundred reads will hit the limit even though its average rate is low. Spread
bulk reads over time.

## Raising a limit

Enterprise plans can raise the limits per service account. The request goes to
support with the account id and the expected peak rate. Limits are never raised
for a personal token, because a personal token usually indicates a script that
should move to a service account.

## Retry policy for SDKs

The official client retries `429` and `503` responses up to three times with
exponential backoff. It honors `Retry-After` when present and never retries a
write that has no idempotency key.

## Limits on the stream endpoint

The live stream at `/v1/projects/{project_id}/runs/{run_id}/stream` counts as one
read request when it opens. Each event after that is free. A client may hold
at most five open streams per token. A sixth stream returns `429` with the code
`STREAM_LIMIT_REACHED`, and the oldest stream is not closed to make room.

## Limits and load tests

Rate limits protect the control plane. They are unrelated to the request budget
on a target, which controls the traffic the load generator sends to your
system under test. Raising one does not change the other.
