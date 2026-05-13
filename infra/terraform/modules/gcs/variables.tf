variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "env" {
  description = "Environment (dev or prod)"
  type        = string
}

variable "location" {
  description = "GCS bucket location (regional or multi-regional)"
  type        = string
  default     = "US"
}
