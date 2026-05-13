variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

# R6-C5: required for common_labels on taggable resources
variable "env" {
  description = "Environment (dev or prod)"
  type        = string
}

variable "subnet_cidr" {
  description = "CIDR range for the subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "connector_cidr" {
  description = "CIDR range for the Serverless VPC Access connector"
  type        = string
  default     = "10.8.0.0/28"
}
