output "dataset_id" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.testlyn_metrics.dataset_id
}

output "samples_table_id" {
  description = "samples_1s table full ID"
  value       = "${var.project_id}.${google_bigquery_dataset.testlyn_metrics.dataset_id}.${google_bigquery_table.samples_1s.table_id}"
}

output "runs_summary_table_id" {
  description = "runs_summary table full ID"
  value       = "${var.project_id}.${google_bigquery_dataset.testlyn_metrics.dataset_id}.${google_bigquery_table.runs_summary.table_id}"
}
