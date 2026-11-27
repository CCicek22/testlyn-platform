# Testlyn — External Setup Checklist

Phase 1 vertical slice runs locally with mocks/stubs. To get to a real deploy, work through this list.

## 0. Local dev (no external accounts needed)

```bash
# Install
pnpm install
uv sync --all-packages

# Spin up Postgres + Redis + BQ emulator
docker compose -f infra/docker-compose.dev.yml up -d

# Migrate
uv run --package testlyn-api alembic upgrade head

# Dev servers
pnpm turbo run dev
```

API: <http://localhost:8080>, Web: <http://localhost:3000>.

`DEV_AUTH_BYPASS=true` skips Identity Platform JWT verify and signs you in as `dev@testlyn.io`.

## 1. GCP project

- [ ] Get the actual GCP project ID (current placeholder: `example-project`).
- [ ] Set `gcloud config set project <id>`.
- [ ] Enable APIs: `compute`, `run`, `cloudbuild`, `cloudtasks`, `cloudscheduler`, `bigquery`, `sqladmin`, `secretmanager`, `artifactregistry`, `identitytoolkit`, `aiplatform`, `redis`, `storage`.
- [ ] Create Terraform state bucket: `gsutil mb -p <id> -l us-central1 gs://testlyn-tfstate`.
- [ ] Set budget alerts on label `app=testlyn`: $50 / $200 / $500.

## 2. Identity Platform

- [ ] In GCP console → Identity Platform → enable.
- [ ] Add providers: Email/Password, Google, GitHub.
- [ ] Copy Firebase config → drop into `apps/web/.env.local` (`NEXT_PUBLIC_FIREBASE_*`).
- [ ] Set `FIREBASE_PROJECT_ID` + audience in `apps/api/.env`.

## 3. Stripe

- [ ] Create Stripe account (test mode initially).
- [ ] Create products: Hobby ($19/mo), Pro ($99/mo), Business ($299/mo). Free is no Stripe product. Enterprise = manual contract.
- [ ] Copy price IDs → `STRIPE_PRICE_*` env vars.
- [ ] Configure webhook endpoint `https://api.testlyn.io/v1/webhooks/stripe` (or ngrok URL for local), copy signing secret.

## 4. SendGrid

- [ ] Create account, verify sender domain `testlyn.io`.
- [ ] Create API key with Mail Send scope, store in Secret Manager.
- [ ] (Optional Phase 1) create transactional templates: welcome, daily-digest.

## 5. Gemini / Vertex AI

- [ ] Enable Vertex AI API on the GCP project.
- [ ] No API key needed — service account `testlyn-report@` gets `roles/aiplatform.user` via Terraform.

## 6. GitHub repo + CI

- [ ] Push to `github.com/CCicek22/testlyn-platform` (default branch `main`).
- [ ] In repo settings → secrets → add `GCP_WIF_PROVIDER`, `GCP_SA_EMAIL`, `GCP_PROJECT_ID`.
- [ ] Cloud Build connect to GitHub repo, or use GitHub Actions workflows under `.github/workflows/`.

## 7. Terraform apply

```bash
cd infra/terraform/envs/dev
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Order matters first time:
1. APIs + IAM + service accounts
2. Network + Cloud SQL + Redis + BQ + GCS
3. Artifact Registry (so Cloud Build can push)
4. Cloud Run services + Jobs (need pushed images first — circular bootstrap; use placeholder image, then redeploy)
5. Cloud Tasks + Scheduler

## 8. Domain (testlyn.io)

- [ ] Register domain.
- [ ] Cloud DNS zone in the GCP project.
- [ ] Cloud Run domain mapping for `testlyn.io` → web, `api.testlyn.io` → api.
