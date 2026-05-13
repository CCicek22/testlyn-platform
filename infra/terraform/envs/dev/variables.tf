variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
  default     = "example-project-prod"
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

variable "db_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_password" {
  description = "Postgres user password"
  type        = string
  sensitive   = true
  default     = "change-me-before-apply"
}

variable "api_image" {
  description = "Container image for the API service"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project-prod/testlyn/api:latest"
}

variable "web_image" {
  description = "Container image for the web service"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project-prod/testlyn/web:latest"
}

variable "engine_image" {
  description = "Container image for the engine job"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project-prod/testlyn/engine:latest"
}

variable "engine_playwright_image" {
  description = "Container image for the Playwright engine job (Phase 2)"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project-prod/testlyn/engine-playwright:latest"
}

variable "engine_a11y_image" {
  description = "Container image for the a11y engine job (Phase 2)"
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project-prod/testlyn/engine-a11y:latest"
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
