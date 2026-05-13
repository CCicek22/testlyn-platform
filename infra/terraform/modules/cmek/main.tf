# ---------------------------------------------------------------------------
# CMEK module — Customer-Managed Encryption Keys
#
# Creates (or accepts) a KMS key and binds it to:
#   - Cloud SQL (testlyn-pg-<env>)
#   - GCS buckets (testlyn-prod-*)
#   - BigQuery dataset (testlyn_metrics)
#
# Usage:
#   module "cmek" {
#     source        = "../../modules/cmek"
#     project_id    = var.gcp_project_id
#     region        = var.region
#     env           = var.env
#     cmek_key_name = var.cmek_key_name   # empty = auto-create
#   }
#
# After apply, set GCP_CMEK_KEY_NAME = module.cmek.key_name in the Cloud Run
# environment so the /v1/orgs/{org_id}/cmek endpoint can surface it.
# ---------------------------------------------------------------------------

locals {
  # Use provided key or the auto-created one.
  effective_key = (
    var.cmek_key_name != ""
    ? var.cmek_key_name
    : (
      length(google_kms_crypto_key.testlyn) > 0
      ? google_kms_crypto_key.testlyn[0].id
      : ""
    )
  )
  create_key = var.cmek_key_name == ""
}

# ── Key ring ────────────────────────────────────────────────────────────────

resource "google_kms_key_ring" "testlyn" {
  count    = local.create_key ? 1 : 0
  project  = var.project_id
  name     = "testlyn-${var.env}"
  location = var.region
}

# ── CryptoKey ───────────────────────────────────────────────────────────────

resource "google_kms_crypto_key" "testlyn" {
  count           = local.create_key ? 1 : 0
  name            = "testlyn-${var.env}-key"
  key_ring        = google_kms_key_ring.testlyn[0].id
  rotation_period = var.rotation_period
  purpose         = "ENCRYPT_DECRYPT"

  labels = {
    app        = "testlyn"
    phase      = "4"
    env        = var.env
    managed-by = "terraform"
  }
}

# ── IAM: Cloud SQL service account ──────────────────────────────────────────

data "google_project" "project" {
  project_id = var.project_id
}

resource "google_kms_crypto_key_iam_member" "cloud_sql" {
  count         = local.create_key ? 1 : 0
  crypto_key_id = google_kms_crypto_key.testlyn[0].id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloud-sql.iam.gserviceaccount.com"
}

# ── IAM: GCS service account ────────────────────────────────────────────────

resource "google_kms_crypto_key_iam_member" "gcs" {
  count         = local.create_key ? 1 : 0
  crypto_key_id = google_kms_crypto_key.testlyn[0].id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.project.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# ── IAM: BigQuery service account ───────────────────────────────────────────

resource "google_kms_crypto_key_iam_member" "bigquery" {
  count         = local.create_key ? 1 : 0
  crypto_key_id = google_kms_crypto_key.testlyn[0].id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.project.number}@bigquery-encryption.iam.gserviceaccount.com"
}

# ── BYOK path: grant same permissions to the provided key ───────────────────
# When cmek_key_name is non-empty we only manage IAM on the provided key.
# The key ring and crypto key resources are not created.

resource "google_kms_crypto_key_iam_member" "cloud_sql_byok" {
  count         = local.create_key ? 0 : 1
  crypto_key_id = var.cmek_key_name
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloud-sql.iam.gserviceaccount.com"
}

resource "google_kms_crypto_key_iam_member" "gcs_byok" {
  count         = local.create_key ? 0 : 1
  crypto_key_id = var.cmek_key_name
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.project.number}@gs-project-accounts.iam.gserviceaccount.com"
}

resource "google_kms_crypto_key_iam_member" "bigquery_byok" {
  count         = local.create_key ? 0 : 1
  crypto_key_id = var.cmek_key_name
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.project.number}@bigquery-encryption.iam.gserviceaccount.com"
}
