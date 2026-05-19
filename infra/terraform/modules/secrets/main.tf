locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }

  # Secrets without env suffix are shared across tiers (one slot, one canonical
  # version). Per-env secrets (chat INTERNAL_TOKEN) are explicit so dev/prod
  # tokens never collide.
  secrets = {
    "testlyn-db-password"               = "Cloud SQL Postgres password for testlyn API"
    "testlyn-stripe-secret-key"         = "Stripe secret key"
    "testlyn-stripe-webhook-secret"     = "Stripe webhook signing secret"
    "testlyn-sendgrid-api-key"          = "SendGrid API key"
    "testlyn-firebase-service-account"  = "Firebase Admin SDK service account JSON"
    "testlyn-internal-token-${var.env}" = "Service-to-service shared secret for testlyn-chat → testlyn-api"
  }
}

resource "google_secret_manager_secret" "secrets" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = each.key

  labels = local.common_labels

  replication {
    auto {}
  }
}
