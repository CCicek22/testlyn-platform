# Runbook: certificate rotation

Owner: Lantern team. Covers the TLS certificates for the public `gate` host and
the internal `relay` mesh.

## Schedule

Public certificates are issued by the internal authority with a 90 day
lifetime. The rotation job starts 21 days before expiry. The internal mesh
certificates last 30 days and rotate every 10 days.

The `CertExpiryWarning` alert fires 14 days before a public certificate
expires. Treat it as a deadline, not as noise.

## Rotating a public certificate

Generate the new key pair inside the secret store, never on a laptop. Request
the certificate with the workflow below.

```sh
brackctl certs request --host gate.example.com --profile public --wait
```

When the request completes, the new certificate is stored under the name
`gate-tls-next`. Load it into the load balancer as a second certificate. Check
the handshake with the staging client before you change the default.

Swap the default only after both certificates are present on every zone. The
old certificate stays attached for 24 hours so that clients with cached
chains keep working.

## Mesh certificates

Mesh certificates rotate automatically. The `relay` sidecar requests a new
certificate when half of its lifetime has passed. If a sidecar cannot reach the
authority, it keeps using the current certificate until expiry and logs
`MESH-CERT-RENEW-FAILED`.

Check the sidecar logs for that code after any network change. A firewall rule
that blocks the authority port 8443 causes the error without any other symptom.

## Common mistakes

Do not paste a private key into a ticket or a chat. If a key leaks, revoke the
certificate first with `brackctl certs revoke`, then request a replacement.

Do not rotate the internal authority root during business hours. The root
change touches every workload, so it needs a planned window and a rollback
plan.

## Verification

Run `brackctl certs check --all`. The output lists each host, the expiry date
in UTC, and the fingerprint. Record the new fingerprint in the rotation log so
that the next rotation can compare against it.
