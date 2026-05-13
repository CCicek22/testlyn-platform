locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }

  versioned_buckets = toset(["testlyn-prod-scripts", "testlyn-prod-results"])

  all_buckets = toset([
    "testlyn-prod-scripts",
    "testlyn-prod-results",
    "testlyn-prod-reports",
    "testlyn-prod-logs",
    "testlyn-prod-spool",
  ])
}

resource "google_storage_bucket" "buckets" {
  for_each = local.all_buckets

  project                     = var.project_id
  name                        = each.value
  location                    = var.location
  force_destroy               = var.env == "prod" ? false : true
  uniform_bucket_level_access = true

  labels = local.common_labels

  versioning {
    enabled = contains(tolist(local.versioned_buckets), each.value)
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = var.env == "prod" ? 5 : 2
      with_state         = "ARCHIVED"
    }
  }
}
