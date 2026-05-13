variable "project_id" {
  description = "GCP project ID (e.g. example-project)"
  type        = string
}

variable "region" {
  description = "GCP region for the KMS key ring"
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Deployment environment (dev | staging | prod)"
  type        = string
}

variable "cmek_key_name" {
  description = <<-EOT
    Optional: fully-qualified KMS CryptoKey resource name for CMEK.
    Format: projects/<proj>/locations/<region>/keyRings/<ring>/cryptoKeys/<key>
    When empty string, the module creates a Google-managed key ring + key
    and returns its name as output.  Pass a non-empty value to use a
    customer-supplied key (BYOK scenario).
  EOT
  type    = string
  default = ""
}

variable "rotation_period" {
  description = "Automatic key rotation period (ISO 8601 duration string)"
  type        = string
  default     = "7776000s" # 90 days
}
