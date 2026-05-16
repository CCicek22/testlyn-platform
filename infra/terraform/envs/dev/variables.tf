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

variable "api_image" {
  description = "Container image for the API service"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project/testlyn/api:latest"
}

variable "web_image" {
  description = "Container image for the web service"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project/testlyn/web:latest"
}

variable "engine_image" {
  description = "Container image for the engine job"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project/testlyn/engine:latest"
}

variable "engine_playwright_image" {
  description = "Container image for the Playwright engine job (Phase 2)"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project/testlyn/engine-playwright:latest"
}

variable "engine_a11y_image" {
  description = "Container image for the a11y engine job (Phase 2)"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project/testlyn/engine-a11y:latest"
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
