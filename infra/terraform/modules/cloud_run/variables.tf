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

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "image" {
  description = "Container image URL"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for this Cloud Run service"
  type        = string
}

variable "vpc_connector_id" {
  description = "VPC Access Connector ID (legacy). Leave empty to use direct VPC egress via network_interfaces."
  type        = string
  default     = ""
}

variable "network_interfaces" {
  description = "Direct VPC egress network interfaces. Mutually exclusive with vpc_connector_id."
  type = list(object({
    network    = string
    subnetwork = string
  }))
  default = []
}

variable "min_instances" {
  description = "Minimum number of instances (0 for scale-to-zero, 1 for warm starts)"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

variable "cpu" {
  description = "CPU limit"
  type        = string
  default     = "1000m"
}

variable "memory" {
  description = "Memory limit"
  type        = string
  default     = "512Mi"
}

variable "port" {
  description = "Container port"
  type        = number
  default     = 8080
}

variable "health_check_path" {
  description = "HTTP path for health checks"
  type        = string
  default     = "/health"
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated (public) access"
  type        = bool
  default     = false
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
