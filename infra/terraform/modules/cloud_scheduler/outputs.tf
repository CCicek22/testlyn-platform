output "spool_replay_job_name" {
  description = "Cloud Scheduler spool replay job name"
  value       = google_cloud_scheduler_job.spool_replay.name
}
