variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "env" {
  description = "Environment (dev or prod)"
  type        = string
}

variable "github_wif_sa_email" {
  description = "Service account email used by GitHub Actions WIF (optional)"
  type        = string
  default     = ""
}
