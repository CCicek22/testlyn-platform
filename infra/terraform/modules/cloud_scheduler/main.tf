locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }
}

resource "google_cloud_scheduler_job" "spool_replay" {
  project     = var.project_id
  name        = "testlyn-spool-replay"
  description = "Hourly spool replay — reprocess any BQ-spooled metric batches"
  region      = var.region
  schedule    = "0 * * * *"
  time_zone   = "UTC"

  http_target {
    http_method = "POST"
    uri         = "${var.api_base_url}/v1/internal/spool/replay"

    oidc_token {
      service_account_email = var.scheduler_sa_email
      audience              = var.api_base_url
    }
  }

  retry_config {
    retry_count          = 3
    min_backoff_duration = "5s"
    max_backoff_duration = "300s"
    max_doublings        = 2
  }
}
