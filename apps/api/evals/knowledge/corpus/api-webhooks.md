# API notes: webhooks

Webhooks send a POST request to your endpoint when a run changes state. They
are configured per project under Settings, Webhooks, or with the API at
`/v1/projects/{project_id}/webhooks`.

## Payload

Each delivery is a JSON object with the event type, the run id, the new state
and a `delivery_id`. The delivery id is stable across retries, so a receiver can
use it to detect duplicates. The event types are `run.started`, `run.finished`
and `run.aborted`.

Payloads never include request bodies, response bodies or headers from the
system under test. They carry only the summary numbers and the link to the
report.

## Signatures

Every delivery carries the header `Brackwater-Signature`, which is an
HMAC-SHA256 of the raw body using the webhook secret. Compute the HMAC over the
bytes you received, not over re-serialized JSON. Reject any delivery whose
signature does not match, and compare signatures in constant time.

Rotate a secret from the webhook page. The old secret keeps signing for 24
hours after rotation, so receivers can switch without dropping events.

## Retries

The platform expects a 2xx response within 10 seconds. Any other response, or
no response, schedules a retry with exponential backoff: 30 seconds, 2 minutes,
10 minutes, 1 hour, then 6 hours. After 8 attempts the delivery is dropped and
appears in the webhook log as `exhausted`.

Deliveries can arrive out of order, especially across retries. Sort by the
run's `updated_at` value instead of arrival time.

## Local testing

Use the `replay` command to resend a stored delivery to a local endpoint. The
replay keeps the original `delivery_id` and signs with the current secret.

## Ordering guarantees

The platform guarantees at-least-once delivery. It does not guarantee order.
A `run.finished` event can arrive before a `run.started` event if the first
delivery was retried. The payload carries the state at the time the event was
generated, so a receiver that stores the latest state should compare
`updated_at` before overwriting.

## Disabling a webhook

A webhook that fails 50 deliveries in a row is disabled automatically. The
project owner receives an email, and the webhook page shows the reason
`consecutive-failures`. Re-enable it after the endpoint is fixed. Deliveries
that were queued while it was disabled are not sent again.
