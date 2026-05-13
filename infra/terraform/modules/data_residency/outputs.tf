output "region" {
  description = "Validated GCP region string."
  value       = var.region
}

output "bq_location" {
  description = "BigQuery dataset location (US | EU | ASIA)."
  value       = local.cfg.bq_location
}

output "gcs_location" {
  description = "GCS bucket location (US | EU | ASIA)."
  value       = local.cfg.gcs_location
}

output "display_name" {
  description = "Human-readable region name for UI display."
  value       = local.cfg.display_name
}

output "gdpr_zone" {
  description = "True when the region is in a GDPR-regulated jurisdiction."
  value       = local.cfg.gdpr_zone
}
