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
  default     = "prod"
}

variable "db_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-g1-small"
}

variable "db_password" {
  description = "Postgres user password"
  type        = string
  sensitive   = true
}

variable "api_image" {
  description = "Container image for the API service"
  type        = string
}

variable "web_image" {
  description = "Container image for the web service"
  type        = string
}

variable "engine_image" {
  description = "Container image for the engine job"
  type        = string
}

variable "engine_playwright_image" {
  description = "Container image for the Playwright engine job (Phase 2)"
  type        = string
}

variable "engine_a11y_image" {
  description = "Container image for the a11y engine job (Phase 2)"
  type        = string
}

variable "billing_account_id" {
  description = "GCP billing account ID (XXXXXX-XXXXXX-XXXXXX format)"
  type        = string
}

variable "github_wif_sa_email" {
  description = "Service account email used by GitHub Actions WIF"
  type        = string
  default     = ""
}
