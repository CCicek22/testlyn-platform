output "secret_ids" {
  description = "Map of secret name to Secret Manager secret ID"
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.secret_id }
}

output "db_password_secret_id" {
  description = "Secret Manager secret ID for the database password"
  value       = google_secret_manager_secret.secrets["testlyn-db-password"].secret_id
}
