variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "project_number" {
  description = "GCP project number (for billing budget filter)"
  type        = string
}

variable "env" {
  description = "Environment (dev or prod)"
  type        = string
}

variable "billing_account_id" {
  description = "GCP billing account ID"
  type        = string
}

variable "budget_usd_threshold_1" {
  description = "First budget alert threshold in USD"
  type        = number
  default     = 50
}

variable "budget_usd_threshold_2" {
  description = "Second budget alert threshold in USD"
  type        = number
  default     = 200
}

variable "budget_usd_threshold_3" {
  description = "Max/third budget alert threshold in USD"
  type        = number
  default     = 500
}

variable "notification_channel_ids" {
  description = "List of Cloud Monitoring notification channel IDs for budget alerts"
  type        = list(string)
  default     = []
}
