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

variable "max_dispatches_per_second" {
  description = "Max task dispatches per second"
  type        = number
  default     = 100
}

variable "max_concurrent_dispatches" {
  description = "Max concurrent task dispatches"
  type        = number
  default     = 50
}

variable "max_attempts" {
  description = "Max retry attempts (-1 = unlimited)"
  type        = number
  default     = 5
}
