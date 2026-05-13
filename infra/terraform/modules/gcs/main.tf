locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }

  versioned_buckets = toset(["testlyn-${var.env}-scripts", "testlyn-${var.env}-results"])

  all_buckets = toset([
    "testlyn-${var.env}-scripts",
    "testlyn-${var.env}-results",
    "testlyn-${var.env}-reports",
    "testlyn-${var.env}-logs",
    "testlyn-${var.env}-spool",
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
    enabled = contains(tolist(local.versioned_buckets), each.key)
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
