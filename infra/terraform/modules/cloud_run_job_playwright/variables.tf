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

variable "job_name" {
  description = "Cloud Run Job name (must start with testlyn-)"
  type        = string
  default     = "testlyn-engine-playwright"
}

variable "image" {
  description = "Container image URL (engine-playwright)"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for this Cloud Run Job"
  type        = string
}

variable "vpc_connector_id" {
  description = "VPC Access Connector ID"
  type        = string
}

# Playwright requires more resources than k6 (browser + sidecar)
variable "cpu" {
  description = "CPU limit"
  type        = string
  default     = "4000m" # 4 vCPU per spec
}

variable "memory" {
  description = "Memory limit"
  type        = string
  default     = "16Gi" # 16 GB per spec
}

variable "timeout_seconds" {
  description = "Maximum job execution time in seconds"
  type        = number
  default     = 3600
}

variable "max_retries" {
  description = "Maximum task retry count"
  type        = number
  default     = 0
}

variable "parallelism" {
  description = "Maximum concurrent tasks"
  type        = number
  default     = 1
}

variable "env_vars" {
  description = "Non-secret environment variables"
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
