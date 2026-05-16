locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }
}

resource "google_bigquery_dataset" "testlyn_metrics" {
  project                    = var.project_id
  dataset_id                 = "testlyn_metrics"
  friendly_name              = "Testlyn Metrics"
  description                = "Load test metric aggregates and run summaries"
  location                   = "US"
  delete_contents_on_destroy = var.env == "prod" ? false : true

  labels = local.common_labels
}

resource "google_bigquery_table" "samples_1s" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.testlyn_metrics.dataset_id
  table_id   = "samples_1s"

  deletion_protection = var.env == "prod" ? true : false

  labels = local.common_labels

  time_partitioning {
    type                     = "DAY"
    field                    = "window_start"
    expiration_ms            = 7776000000 # 90 days
    require_partition_filter = false
  }

  clustering = ["run_id", "metric"]

  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED", description = "Test run ID injected by Cloud Run Job" },
    { name = "org_id", type = "STRING", mode = "REQUIRED", description = "Organization ID" },
    { name = "product", type = "STRING", mode = "REQUIRED", description = "Product type: load in Phase 1" },
    { name = "region", type = "STRING", mode = "REQUIRED", description = "GCP region where job ran" },
    { name = "window_start", type = "TIMESTAMP", mode = "REQUIRED", description = "Start of the 1-second tumbling window (UTC)" },
    { name = "metric", type = "STRING", mode = "REQUIRED", description = "Metric name e.g. http_req_duration" },
    { name = "metric_type", type = "STRING", mode = "REQUIRED", description = "trend | counter | gauge | rate" },
    { name = "tag_method", type = "STRING", mode = "NULLABLE", description = "HTTP method tag" },
    { name = "tag_status", type = "STRING", mode = "NULLABLE", description = "HTTP status code tag" },
    { name = "tag_scenario", type = "STRING", mode = "NULLABLE", description = "k6 scenario tag" },
    { name = "tag_group", type = "STRING", mode = "NULLABLE", description = "k6 group tag" },
    { name = "tag_name", type = "STRING", mode = "NULLABLE", description = "URL or named request, normalized" },
    { name = "tag_extra", type = "JSON", mode = "NULLABLE", description = "Any tags beyond the indexed ones" },
    { name = "count", type = "INT64", mode = "NULLABLE", description = "Sample count in window (trend metrics)" },
    { name = "sum_value", type = "FLOAT64", mode = "NULLABLE", description = "Sum of values in window" },
    { name = "min_value", type = "FLOAT64", mode = "NULLABLE", description = "Min value in window" },
    { name = "max_value", type = "FLOAT64", mode = "NULLABLE", description = "Max value in window" },
    { name = "p50", type = "FLOAT64", mode = "NULLABLE", description = "50th percentile" },
    { name = "p90", type = "FLOAT64", mode = "NULLABLE", description = "90th percentile" },
    { name = "p95", type = "FLOAT64", mode = "NULLABLE", description = "95th percentile" },
    { name = "p99", type = "FLOAT64", mode = "NULLABLE", description = "99th percentile" },
    { name = "delta", type = "FLOAT64", mode = "NULLABLE", description = "Sum-of-increments for counter; latest for gauge" },
    { name = "rate_per_sec", type = "FLOAT64", mode = "NULLABLE", description = "Success rate for rate metrics in this window" },
    { name = "inserted_at", type = "TIMESTAMP", mode = "NULLABLE", description = "Row insertion timestamp" },
  ])
}

resource "google_bigquery_table" "runs_summary" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.testlyn_metrics.dataset_id
  table_id   = "runs_summary"

  deletion_protection = var.env == "prod" ? true : false

  labels = local.common_labels

  time_partitioning {
    type                     = "DAY"
    field                    = "started_at"
    expiration_ms            = 63072000000 # 730 days
    require_partition_filter = false
  }

  clustering = ["org_id", "run_id"]

  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED", description = "Test run ID" },
    { name = "org_id", type = "STRING", mode = "REQUIRED", description = "Organization ID" },
    { name = "product", type = "STRING", mode = "REQUIRED", description = "Product type" },
    { name = "region", type = "STRING", mode = "REQUIRED", description = "GCP region" },
    { name = "started_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Run start timestamp" },
    { name = "finished_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Run finish timestamp" },
    { name = "vus_max", type = "INT64", mode = "NULLABLE", description = "Peak VU count" },
    { name = "iterations", type = "INT64", mode = "NULLABLE", description = "Total k6 iterations" },
    { name = "http_reqs", type = "INT64", mode = "NULLABLE", description = "Total HTTP requests" },
    { name = "http_failed", type = "INT64", mode = "NULLABLE", description = "Total failed HTTP requests" },
    { name = "data_sent", type = "INT64", mode = "NULLABLE", description = "Total bytes sent" },
    { name = "data_received", type = "INT64", mode = "NULLABLE", description = "Total bytes received" },
    { name = "summary_json", type = "JSON", mode = "NULLABLE", description = "Full k6 --summary-export blob" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "completed | partial | failed" },
  ])
}
