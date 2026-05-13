variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Environment (dev or prod)"
  type        = string
}

variable "api_base_url" {
  description = "Base URL of the Testlyn API Cloud Run service"
  type        = string
}

variable "scheduler_sa_email" {
  description = "Service account email Cloud Scheduler uses to invoke Cloud Run"
  type        = string
}
