# ---------------------------------------------------------------------------
# data_residency module — Region pin matrix
#
# Validates and surfaces per-region configuration used by all other modules.
# All resources in a Testlyn deployment share a single region; this module
# is the single source of truth for region-scoped settings.
#
# Supported regions (Phase 4 scaffold):
#   us-central1     — US     — BigQuery multi-region: US
#   europe-west4    — EU     — BigQuery multi-region: EU
#   asia-southeast1 — APAC   — BigQuery multi-region: ASIA
#
# Usage:
#   module "residency" {
#     source = "../../modules/data_residency"
#     region = var.region        # validated by the variable block
#   }
#
#   # Then reference:
#   module.residency.region           # e.g. "europe-west4"
#   module.residency.bq_location      # e.g. "EU"
#   module.residency.gcs_location     # e.g. "EU"
#   module.residency.display_name     # e.g. "Europe (Netherlands)"
# ---------------------------------------------------------------------------

locals {
  # Region matrix — extend this table as new regions are enabled.
  region_matrix = {
    "us-central1" = {
      bq_location  = "US"
      gcs_location = "US"
      display_name = "United States (Iowa)"
      gdpr_zone    = false
    }
    "europe-west4" = {
      bq_location  = "EU"
      gcs_location = "EU"
      display_name = "Europe (Netherlands)"
      gdpr_zone    = true
    }
    "asia-southeast1" = {
      bq_location  = "ASIA"
      gcs_location = "ASIA"
      display_name = "Asia Pacific (Singapore)"
      gdpr_zone    = false
    }
  }

  cfg = local.region_matrix[var.region]
}
