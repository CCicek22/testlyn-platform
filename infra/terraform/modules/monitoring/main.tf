locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }
}

# Budget alert for testlyn-labeled resources
resource "google_billing_budget" "testlyn" {
  billing_account = var.billing_account_id
  display_name    = "Testlyn Phase 1 Budget (${var.env})"

  budget_filter {
    projects = ["projects/${var.project_number}"]
    labels = {
      app = "testlyn"
    }
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd_threshold_3)
    }
  }

  threshold_rules {
    threshold_percent = var.budget_usd_threshold_1 / var.budget_usd_threshold_3
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = var.budget_usd_threshold_2 / var.budget_usd_threshold_3
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  all_updates_rule {
    pubsub_topic                     = google_pubsub_topic.budget_alerts.id
    schema_version                   = "1.0"
    monitoring_notification_channels = var.notification_channel_ids
  }
}

resource "google_pubsub_topic" "budget_alerts" {
  project = var.project_id
  name    = "testlyn-budget-alerts-${var.env}"

  labels = local.common_labels
}

# Alert policy: sidecar spool size > 100 MB for 5 minutes
resource "google_monitoring_alert_policy" "sidecar_spool_size" {
  project      = var.project_id
  display_name = "Testlyn Sidecar Spool Size High"
  combiner     = "OR"

  conditions {
    display_name = "Sidecar spool size > 100 MB for 5 min"

    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/testlyn/sidecar/spool_size_bytes\" AND resource.type=\"generic_task\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 104857600 # 100 MB

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }

  user_labels = local.common_labels
}

# Log-based metric for API 5xx errors
resource "google_logging_metric" "api_5xx" {
  project = var.project_id
  name    = "testlyn/api/5xx_count"
  filter  = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"testlyn-api\" AND httpRequest.status>=500"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    labels {
      key         = "status"
      value_type  = "STRING"
      description = "HTTP status code"
    }
  }

  label_extractors = {
    "status" = "EXTRACT(httpRequest.status)"
  }
}
