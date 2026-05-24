# REMOVED 2026-05-24 (Option B) — api_url, web_url, chat_url, engine_job_name,
# chat_domain outputs dropped with their respective Cloud Run modules.
# CI (gcloud run deploy) is the authoritative source for service URLs.

output "db_host" {
  description = "Postgres host (self-hosted PgBouncer on db-vm VM)"
  value       = var.db_host
}

output "redis_url" {
  description = "Redis connection URL (self-hosted on db-vm VM)"
  value       = var.redis_url
  sensitive   = true
}

output "bq_dataset_id" {
  description = "BigQuery dataset ID"
  value       = module.bigquery.dataset_id
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker URL"
  value       = module.artifact_registry.repository_url
}

output "api_sa_email" {
  description = "API service account email"
  value       = module.iam.api_sa_email
}

output "runner_sa_email" {
  description = "Runner service account email"
  value       = module.iam.runner_sa_email
}

output "chat_sa_email" {
  description = "Chat service account email"
  value       = module.iam.chat_sa_email
}
