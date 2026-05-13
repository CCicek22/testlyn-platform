output "violations_cache_table_id" {
  description = "BQ table ID for a11y_violations_cache"
  value       = google_bigquery_table.a11y_violations_cache.table_id
}
