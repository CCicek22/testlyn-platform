#!/usr/bin/env bash
# bootstrap.sh — idempotent GCP project setup for Testlyn
# Usage: GCP_PROJECT_ID=example-project ./infra/scripts/bootstrap.sh
# Requires: gcloud CLI authenticated with Owner/Editor on the project
set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set}"

REGION="${REGION:-us-central1}"
STATE_BUCKET="testlyn-tfstate"

echo "==> Bootstrapping Testlyn on project: ${GCP_PROJECT_ID}"
echo "    Region: ${REGION}"
echo "    State bucket: gs://${STATE_BUCKET}"

gcloud config set project "${GCP_PROJECT_ID}"

# ── Enable APIs ──────────────────────────────────────────────────────────────
APIS=(
  run.googleapis.com
  sqladmin.googleapis.com
  redis.googleapis.com
  bigquery.googleapis.com
  bigquerystorage.googleapis.com
  storage.googleapis.com
  cloudtasks.googleapis.com
  cloudscheduler.googleapis.com
  artifactregistry.googleapis.com
  secretmanager.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  vpcaccess.googleapis.com
  servicenetworking.googleapis.com
  logging.googleapis.com
  monitoring.googleapis.com
  cloudresourcemanager.googleapis.com
  identitytoolkit.googleapis.com
  aiplatform.googleapis.com
)

echo "==> Enabling ${#APIS[@]} APIs..."
gcloud services enable "${APIS[@]}" --project="${GCP_PROJECT_ID}"

# ── Create Terraform state bucket ────────────────────────────────────────────
if gsutil ls "gs://${STATE_BUCKET}" &>/dev/null; then
  echo "==> State bucket gs://${STATE_BUCKET} already exists — skipping"
else
  echo "==> Creating state bucket gs://${STATE_BUCKET}..."
  gsutil mb -p "${GCP_PROJECT_ID}" -l "${REGION}" -b on "gs://${STATE_BUCKET}"
  gsutil versioning set on "gs://${STATE_BUCKET}"
  echo "    Versioning enabled."
fi

# ── Prevent public access on state bucket ────────────────────────────────────
gsutil pap set enforced "gs://${STATE_BUCKET}" || true

echo ""
echo "==> Bootstrap complete."
echo "    Next steps:"
echo "    1. cp infra/terraform/envs/dev/terraform.tfvars.example infra/terraform/envs/dev/terraform.tfvars"
echo "    2. Edit terraform.tfvars — fill in real values."
echo "    3. cd infra/terraform/envs/dev && terraform init && terraform plan"
