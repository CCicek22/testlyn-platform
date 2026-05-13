variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "env" {
  description = "Environment (dev or prod)"
  type        = string
}

variable "dataset_id" {
  description = "Existing BigQuery dataset ID (testlyn_metrics)"
  type        = string
  default     = "testlyn_metrics"
}
