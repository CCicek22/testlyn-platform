output "bucket_names" {
  description = "Map of bucket key to bucket name"
  value       = { for k, v in google_storage_bucket.buckets : k => v.name }
}

output "scripts_bucket" {
  description = "GCS bucket for k6 scripts"
  value       = google_storage_bucket.buckets["testlyn-prod-scripts"].name
}

output "results_bucket" {
  description = "GCS bucket for k6 summary JSONs"
  value       = google_storage_bucket.buckets["testlyn-prod-results"].name
}

output "reports_bucket" {
  description = "GCS bucket for PDF reports"
  value       = google_storage_bucket.buckets["testlyn-prod-reports"].name
}

output "logs_bucket" {
  description = "GCS bucket for worker logs"
  value       = google_storage_bucket.buckets["testlyn-prod-logs"].name
}

output "spool_bucket" {
  description = "GCS bucket for BQ-outage spool spillover"
  value       = google_storage_bucket.buckets["testlyn-prod-spool"].name
}
