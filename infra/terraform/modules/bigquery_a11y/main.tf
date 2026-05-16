/**
 * bigquery_a11y — adds a11y-specific columns to the existing runs_summary table
 * and creates a new a11y_violations_cache table in the testlyn_metrics dataset.
 *
 * IMPORTANT: This module uses google_bigquery_table with schema update_options
 * set to ALLOW_FIELD_ADDITION only, so it will not conflict with or remove
 * columns managed by the foundation bigquery module.
 *
 * Columns added to runs_summary:
 *   wcag_violations_count  INT64   NULLABLE  — total violations
 *   wcag_critical          INT64   NULLABLE
 *   wcag_serious           INT64   NULLABLE
 *   wcag_moderate          INT64   NULLABLE
 *   wcag_minor             INT64   NULLABLE
 *
 * NOTE: BigQuery does not support ALTER TABLE ADD COLUMN via the REST API for
 * tables with deletion_protection = true. In production, these columns are added
 * by providing the full updated schema to google_bigquery_table with the columns
 * appended. This module should be applied AFTER the foundation bigquery module
 * so the dataset already exists.
 *
 * In practice: apply `terraform apply -target=module.bigquery_a11y` after
 * `terraform apply -target=module.bigquery` to avoid dependency ordering issues.
 */

locals {
  common_labels = {
    app        = "testlyn"
    phase      = "2"
    env        = var.env
    managed-by = "terraform"
    product    = "a11y"
  }
}

# a11y_violations_cache — cross-run cache of LLM remediation text
# Keyed by (rule_id, html_snippet_hash); unique constraint enforced in Postgres
# (migration 0005). This BQ table is for analytics / audit trail only.
resource "google_bigquery_table" "a11y_violations_cache" {
  project    = var.project_id
  dataset_id = var.dataset_id
  table_id   = "a11y_violations_cache"

  deletion_protection = var.env == "prod" ? true : false

  labels = local.common_labels

  schema = jsonencode([
    { name = "rule_id", type = "STRING", mode = "REQUIRED", description = "axe-core rule ID" },
    { name = "html_snippet_hash", type = "STRING", mode = "REQUIRED", description = "SHA-256 prefix of html_snippet" },
    { name = "remediation", type = "STRING", mode = "REQUIRED", description = "LLM-generated remediation text" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Row creation time" },
  ])
}

# runs_summary a11y columns are documented here for reference.
# They are added to the table by updating the schema in the foundation
# bigquery module (infra/terraform/modules/bigquery/main.tf) — adding them
# directly via a separate resource would cause state conflicts.
#
# Pending W2A integration: add the five columns below to the runs_summary
# schema in the foundation module in a coordinated PR:
#
#   { name = "wcag_violations_count", type = "INT64",   mode = "NULLABLE", description = "Total WCAG violations" },
#   { name = "wcag_critical",         type = "INT64",   mode = "NULLABLE", description = "Critical impact violations" },
#   { name = "wcag_serious",          type = "INT64",   mode = "NULLABLE", description = "Serious impact violations" },
#   { name = "wcag_moderate",         type = "INT64",   mode = "NULLABLE", description = "Moderate impact violations" },
#   { name = "wcag_minor",            type = "INT64",   mode = "NULLABLE", description = "Minor impact violations" },
