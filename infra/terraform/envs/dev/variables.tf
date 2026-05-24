variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
  default     = "example-project"
}

variable "gcp_project_number" {
  description = "GCP project number (numeric, for billing budget)"
  type        = string
  default     = ""
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "db_password" {
  description = "Postgres user password (REQUIRED — sourced from TF_VAR_db_password / Secret Manager). No default to force explicit set."
  type        = string
  sensitive   = true
}

variable "db_host" {
  description = "Postgres host. Live infra: self-hosted PgBouncer on db-vm VM (10.0.0.5)."
  type        = string
  default     = "10.0.0.5"
}

variable "redis_url" {
  description = "Redis connection URL. Live infra: self-hosted Redis on db-vm VM."
  type        = string
  default     = "redis://10.0.0.5:6379/0"
}

variable "api_base_url" {
  description = "Public API base URL — used by cloud_scheduler for HTTP target and OIDC audience"
  type        = string
  default     = "https://api.dev.testlyn.example.com"
}

variable "billing_account_id" {
  description = "GCP billing account ID (XXXXXX-XXXXXX-XXXXXX format)"
  type        = string
  default     = ""
}

variable "github_wif_sa_email" {
  description = "Service account email used by GitHub Actions WIF"
  type        = string
  default     = ""
}

# REMOVED 2026-05-24 (Option B) — variables below were only referenced by
# Cloud Run service/job modules now managed by CI, not Terraform:
#   api_image, web_image, engine_image, engine_playwright_image, engine_a11y_image,
#   chat_image, chat_domain, gemini_model, chat_redis_db, web_base_url
