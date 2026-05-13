output "api_sa_email" {
  description = "testlyn-api service account email"
  value       = google_service_account.sa["testlyn-api"].email
}

output "runner_sa_email" {
  description = "testlyn-runner service account email"
  value       = google_service_account.sa["testlyn-runner"].email
}

output "report_sa_email" {
  description = "testlyn-report service account email"
  value       = google_service_account.sa["testlyn-report"].email
}

output "web_sa_email" {
  description = "testlyn-web service account email"
  value       = google_service_account.sa["testlyn-web"].email
}
