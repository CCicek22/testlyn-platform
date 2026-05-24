output "budget_alerts_topic" {
  description = "Pub/Sub topic ID for budget alerts"
  value       = google_pubsub_topic.budget_alerts.id
}

output "sidecar_spool_alert_policy_name" {
  description = "Cloud Monitoring alert policy name for sidecar spool size (null when cost alerts disabled)"
  value       = one(google_monitoring_alert_policy.sidecar_spool_size[*].name)
}
