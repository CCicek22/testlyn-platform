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
module "network" {
  source     = "../../modules/network"
  project_id = var.gcp_project_id
  region     = var.region

  depends_on = [module.apis]
}

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

# ── Cloud SQL ────────────────────────────────────────────────────────────────
module "cloud_sql" {
  source     = "../../modules/cloud_sql"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env
  db_tier    = var.db_tier

  vpc_id                 = module.network.vpc_id
  private_vpc_connection = module.network.private_vpc_connection
  db_password            = var.db_password

  depends_on = [module.network]
}

# ── Memorystore (Redis) ──────────────────────────────────────────────────────
module "memorystore" {
  source     = "../../modules/memorystore"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  vpc_id                 = module.network.vpc_id
  private_vpc_connection = module.network.private_vpc_connection

  depends_on = [module.network]
}

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

# ── Cloud Run: API service ────────────────────────────────────────────────────
module "cloud_run_api" {
  source     = "../../modules/cloud_run"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  service_name          = "testlyn-api"
  image                 = var.api_image
  service_account_email = module.iam.api_sa_email
  vpc_connector_id      = module.network.connector_id
  min_instances         = 0
  max_instances         = 5
  cpu                   = "1000m"
  memory                = "512Mi"
  port                  = 8080
  health_check_path     = "/health"
  allow_unauthenticated = true

  env_vars = {
    GCP_PROJECT     = var.gcp_project_id
    REGION          = var.region
    ENV             = var.env
    DB_HOST         = module.cloud_sql.private_ip
    DB_NAME         = module.cloud_sql.database_name
    DB_USER         = module.cloud_sql.db_user
    REDIS_URL       = module.memorystore.redis_url
    BQ_DATASET      = module.bigquery.dataset_id
    TASKS_QUEUE     = module.cloud_tasks.queue_name
    SCRIPTS_BUCKET  = module.gcs.scripts_bucket
    RESULTS_BUCKET  = module.gcs.results_bucket
    REPORTS_BUCKET  = module.gcs.reports_bucket
    LOGS_BUCKET     = module.gcs.logs_bucket
  }

  secret_env_vars = {
    DB_PASSWORD = {
      secret  = module.secrets.db_password_secret_id
      version = "latest"
    }
  }

  depends_on = [module.cloud_sql, module.memorystore, module.iam, module.network]
}

# ── Cloud Run: Web service ─────────────────────────────────────────────────
module "cloud_run_web" {
  source     = "../../modules/cloud_run"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  service_name          = "testlyn-web"
  image                 = var.web_image
  service_account_email = module.iam.web_sa_email
  vpc_connector_id      = module.network.connector_id
  min_instances         = 0
  max_instances         = 5
  cpu                   = "1000m"
  memory                = "512Mi"
  port                  = 3000
  health_check_path     = "/api/health"
  allow_unauthenticated = true

  env_vars = {
    NEXT_PUBLIC_API_URL = module.cloud_run_api.service_url
    ENV                 = var.env
  }

  depends_on = [module.cloud_run_api, module.iam, module.network]
}

# ── Cloud Run Job: Engine ──────────────────────────────────────────────────
module "cloud_run_job_engine" {
  source     = "../../modules/cloud_run_job"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  job_name              = "testlyn-engine"
  image                 = var.engine_image
  service_account_email = module.iam.runner_sa_email
  vpc_connector_id      = module.network.connector_id
  cpu                   = "4000m"
  memory                = "16Gi"
  timeout_seconds       = 3600
  max_retries           = 0

  env_vars = {
    GCP_PROJECT    = var.gcp_project_id
    REGION         = var.region
    BQ_DATASET     = module.bigquery.dataset_id
    SCRIPTS_BUCKET = module.gcs.scripts_bucket
    RESULTS_BUCKET = module.gcs.results_bucket
    SPOOL_BUCKET   = module.gcs.spool_bucket
    CALLBACK_URL   = "${module.cloud_run_api.service_url}/v1/internal/runs"
  }

  depends_on = [module.bigquery, module.gcs, module.iam, module.network]
}

# ── Cloud Scheduler ──────────────────────────────────────────────────────────
module "cloud_scheduler" {
  source     = "../../modules/cloud_scheduler"
  project_id = var.gcp_project_id
  region     = var.region
  env        = var.env

  api_base_url       = module.cloud_run_api.service_url
  scheduler_sa_email = module.iam.api_sa_email

  depends_on = [module.cloud_run_api]
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

  depends_on = [module.apis]
}
