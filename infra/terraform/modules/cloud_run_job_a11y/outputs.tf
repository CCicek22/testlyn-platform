output "job_name" {
  description = "Cloud Run Job name for testlyn-engine-a11y"
  value       = google_cloud_run_v2_job.engine_a11y.name
}

output "job_id" {
  description = "Cloud Run Job resource ID"
  value       = google_cloud_run_v2_job.engine_a11y.id
}
