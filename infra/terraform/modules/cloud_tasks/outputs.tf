output "queue_name" {
  description = "Cloud Tasks queue name"
  value       = google_cloud_tasks_queue.testlyn_jobs.name
}

output "queue_id" {
  description = "Cloud Tasks queue ID"
  value       = google_cloud_tasks_queue.testlyn_jobs.id
}
