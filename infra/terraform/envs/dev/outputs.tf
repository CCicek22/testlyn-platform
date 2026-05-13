output "api_url" {
  description = "Cloud Run API service URL"
  value       = module.cloud_run_api.service_url
}

output "web_url" {
  description = "Cloud Run web service URL"
  value       = module.cloud_run_web.service_url
}

output "db_connection_name" {
  description = "Cloud SQL instance connection name"
  value       = module.cloud_sql.instance_connection_name
}

output "redis_url" {
  description = "Memorystore Redis connection URL"
  value       = module.memorystore.redis_url
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
