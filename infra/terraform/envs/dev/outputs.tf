output "api_url" {
  description = "Cloud Run API service URL"
  value       = module.cloud_run_api.service_url
}

output "web_url" {
  description = "Cloud Run web service URL"
  value       = module.cloud_run_web.service_url
}

# DELETED 2026-05-16 — live runs self-hosted on db-vm VM. db_connection_name
# and redis_url outputs removed with cloud_sql / memorystore modules.
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

output "engine_job_name" {
  description = "Cloud Run Job name for the engine"
  value       = module.cloud_run_job_engine.job_name
}

output "api_sa_email" {
  description = "API service account email"
  value       = module.iam.api_sa_email
}

output "runner_sa_email" {
  description = "Runner service account email"
  value       = module.iam.runner_sa_email
}

output "chat_url" {
  description = "Cloud Run chat service URL (run.app — public custom domain is chat_domain)"
  value       = module.cloud_run_chat.service_url
}

output "chat_sa_email" {
  description = "Chat service account email"
  value       = module.iam.chat_sa_email
}

output "chat_domain" {
  description = "Custom domain mapped to testlyn-chat"
  value       = var.chat_domain
}
