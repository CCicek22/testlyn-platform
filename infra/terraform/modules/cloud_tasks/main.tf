locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }
}

resource "google_cloud_tasks_queue" "testlyn_jobs" {
  project  = var.project_id
  name     = "testlyn-jobs"
  location = var.region

  rate_limits {
    max_dispatches_per_second = var.max_dispatches_per_second
    max_concurrent_dispatches = var.max_concurrent_dispatches
  }

  retry_config {
    max_attempts  = var.max_attempts
    min_backoff   = "10s"
    max_backoff   = "300s"
    max_doublings = 4
  }
}
