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

variable "image" {
  description = "Container image URL for testlyn-engine-a11y"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for the a11y Cloud Run Job"
  type        = string
}

variable "vpc_connector_id" {
  description = "VPC Access Connector ID"
  type        = string
}

variable "cpu" {
  description = "CPU limit (2 vCPU for Playwright headless)"
  type        = string
  default     = "2000m"
}

variable "memory" {
  description = "Memory limit (4 GB for Playwright + axe-core)"
  type        = string
  default     = "4Gi"
}

variable "timeout_seconds" {
  description = "Maximum job execution time in seconds (default 30 min)"
  type        = number
  default     = 1800
}

variable "max_retries" {
  description = "Maximum task retry count (0 = no retry; a11y runs are idempotent but retries waste quota)"
  type        = number
  default     = 0
}

variable "env_vars" {
  description = "Non-secret environment variables injected at job creation time"
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Secret Manager-sourced environment variables"
  type = map(object({
    secret  = string
    version = string
  }))
  default = {}
}
