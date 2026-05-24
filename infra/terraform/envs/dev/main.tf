terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}

provider "google-beta" {
  project = var.gcp_project_id
  region  = var.region
}

# ── APIs ────────────────────────────────────────────────────────────────────
module "apis" {
  source     = "../../modules/apis"
  project_id = var.gcp_project_id
}

# ── Network ─────────────────────────────────────────────────────────────────
# REMOVED 2026-05-24 — testlyn-vpc, subnet, connector, and private_ip_range
# were deleted outside TF. Cloud Run services use Direct VPC egress on the
# default VPC; no custom network or Serverless VPC Connector is needed.
# CI owns Cloud Run service/job lifecycle — TF does not manage them.

# ── IAM ─────────────────────────────────────────────────────────────────────
module "iam" {
  source     = "../../modules/iam"
  project_id = var.gcp_project_id
  env        = var.env

  github_wif_sa_email = var.github_wif_sa_email

  depends_on = [module.apis]
}

# ── Artifact Registry ────────────────────────────────────────────────────────
module "artifact_registry" {
  source     = "../../modules/artifact_registry"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  depends_on = [module.apis]
}

# ── Secrets ──────────────────────────────────────────────────────────────────
module "secrets" {
  source     = "../../modules/secrets"
  project_id = var.gcp_project_id
  env        = var.env

  depends_on = [module.apis]
}

# DELETED 2026-05-16 — live runs self-hosted on db-vm VM (10.0.0.5).
# Cloud SQL + Memorystore were torn down by operator; re-introducing these
# modules would either destroy live data or create duplicate stateful
# resources. App reads DB via var.db_host / var.redis_url instead.
#
# module "cloud_sql" {
#   source     = "../../modules/cloud_sql"
#   project_id = var.gcp_project_id
#   region     = var.region
#   env        = var.env
#   db_tier    = var.db_tier
#   vpc_id                 = module.network.vpc_id
#   private_vpc_connection = module.network.private_vpc_connection
#   db_password            = var.db_password
#   depends_on = [module.network]
# }
#
# module "memorystore" {
#   source     = "../../modules/memorystore"
#   project_id = var.gcp_project_id
#   region     = var.region
#   env        = var.env
#   vpc_id                 = module.network.vpc_id
#   private_vpc_connection = module.network.private_vpc_connection
#   depends_on = [module.network]
# }

# ── BigQuery ─────────────────────────────────────────────────────────────────
module "bigquery" {
  source     = "../../modules/bigquery"
  project_id = var.gcp_project_id
  env        = var.env

  depends_on = [module.apis]
}

# ── GCS Buckets ──────────────────────────────────────────────────────────────
module "gcs" {
  source     = "../../modules/gcs"
  project_id = var.gcp_project_id
  env        = var.env

  depends_on = [module.apis]
}

# ── Cloud Tasks ──────────────────────────────────────────────────────────────
module "cloud_tasks" {
  source     = "../../modules/cloud_tasks"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  depends_on = [module.apis]
}

# ── Cloud Run services + jobs — REMOVED 2026-05-24 (Option B) ────────────────
# CI (GitHub Actions / Cloud Build) owns the full Cloud Run service and job
# lifecycle via `gcloud run deploy` / `gcloud run jobs update`. Terraform never
# managed these resources in state; removing them from config eliminates the
# planned-create drift without risking a destructive state import.
#
# Services removed: cloud_run_api, cloud_run_web, cloud_run_chat
# Resource removed: google_cloud_run_domain_mapping.chat
# Jobs removed:     cloud_run_job_engine, cloud_run_job_playwright, cloud_run_job_a11y
#
# NOTE: cloud_run_job_engine creation gap — ci-engine.yml only runs
# `gcloud run jobs update` (with continue-on-error); it does NOT create the job.
# The engine, playwright, and a11y jobs have no automated creation path now.
# Operator must manually `gcloud run jobs create` once, or restore a TF module
# with `lifecycle { ignore_changes = [template[0].containers[0].image] }`.

# ── BigQuery a11y (Phase 2) ───────────────────────────────────────────────────
module "bigquery_a11y" {
  source     = "../../modules/bigquery_a11y"
  project_id = var.gcp_project_id
  env        = var.env
  dataset_id = module.bigquery.dataset_id

  depends_on = [module.bigquery]
}

# ── Cloud Scheduler ──────────────────────────────────────────────────────────
module "cloud_scheduler" {
  source     = "../../modules/cloud_scheduler"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  api_base_url       = var.api_base_url
  scheduler_sa_email = module.iam.api_sa_email

  depends_on = [module.iam]
}

# ── Monitoring ───────────────────────────────────────────────────────────────
module "monitoring" {
  source     = "../../modules/monitoring"
  project_id = var.gcp_project_id
  env        = var.env

  project_number     = var.gcp_project_number
  billing_account_id = var.billing_account_id

  budget_usd_threshold_1 = 50
  budget_usd_threshold_2 = 200
  budget_usd_threshold_3 = 500

  # Disabled in dev: the deploy identity lacks Billing-account perms (budget)
  # and the custom sidecar/spool_size_bytes metric doesn't exist until a load
  # run emits it (alert). Re-enable once both prerequisites are met.
  enable_cost_alerts = false

  depends_on = [module.apis]
}
