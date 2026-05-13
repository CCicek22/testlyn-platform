variable "region" {
  description = <<-EOT
    Deployment region.  Must be one of the supported values:
      us-central1       — United States (default, Phase 1+)
      europe-west4      — Netherlands (EU data residency)
      asia-southeast1   — Singapore (APAC data residency)
    Additional regions added in Phase 4 GA based on customer demand.
  EOT
  type = string

  validation {
    condition = contains(
      ["us-central1", "europe-west4", "asia-southeast1"],
      var.region
    )
    error_message = "region must be one of: us-central1, europe-west4, asia-southeast1"
  }
}
