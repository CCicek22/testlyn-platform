# Testlyn

Developer-first AI test platform. Phase 1 ships load testing.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic, uv |
| Frontend | Node 24 LTS, Next.js 15, React 19, TypeScript, Tailwind v4, shadcn/ui |
| Database | Postgres 16 (Cloud SQL), BigQuery (`testlyn_metrics`) |
| Queue | Cloud Tasks, Cloud Scheduler |
| Load engine | Stock `grafana/k6` + Python BigQuery sidecar (AGPL-safe) |
| Auth | Identity Platform |
| Payments | Stripe |
| Email | SendGrid |
| LLM | Gemini 3.1 Flash-Lite via Vertex AI |
| IaC | Terraform |

## Layout

```
apps/
  api/            FastAPI backend
  web/            Next.js (marketing + dashboard)
  engine/         k6 worker container (stock k6 + Python sidecar)
  report-builder/ PDF + AI summary
packages/
  shared/         TS types (generated from OpenAPI)
  ui/             shadcn/ui components
infra/terraform/  GCP IaC
docs/             Specs, ADRs, build log
```

## Quickstart

See [SETUP.md](./SETUP.md).

## Hard rules

Most important:

- k6 binary is **unmodified**, invoked as subprocess. Never xk6 / custom build.
- `tests` and `test_runs` carry a `product` discriminator column.
- All Postgres access through SQLAlchemy + Alembic. No raw SQL in app code.
- Secrets in Secret Manager only.

## Phase roadmap

- **Phase 1 (active):** Load Testing MVP
- Phase 2: Functional + accessibility
- Phase 3: Synthetic data + security + multi-region
- Phase 4: Mobile + RUM + RBAC + enterprise

## License

© 2026 Mack Cicek. All rights reserved. Source is published for review; no licence is granted.
