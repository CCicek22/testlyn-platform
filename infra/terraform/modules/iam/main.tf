locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }

  service_accounts = {
    "testlyn-api"    = "FastAPI Cloud Run service account"
    "testlyn-runner" = "k6 worker Cloud Run Jobs service account"
    "testlyn-report" = "PDF and AI report builder service account"
    "testlyn-web"    = "Next.js Cloud Run service account"
  }
}

resource "google_service_account" "sa" {
  for_each = local.service_accounts

  project      = var.project_id
  account_id   = each.key
  display_name = each.value
}

# testlyn-api bindings
resource "google_project_iam_member" "api_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

resource "google_project_iam_member" "api_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

resource "google_project_iam_member" "api_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

resource "google_project_iam_member" "api_cloudtasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

resource "google_project_iam_member" "api_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

resource "google_project_iam_member" "api_bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

resource "google_project_iam_member" "api_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

# Vertex AI — the chat coordinator (folded into testlyn-api) calls Gemini via
# google-genai/ADK under the api SA. Previously held by the now-removed
# testlyn-chat SA.
resource "google_project_iam_member" "api_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa["testlyn-api"].email}"
}

# testlyn-runner bindings
resource "google_project_iam_member" "runner_bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.sa["testlyn-runner"].email}"
}

resource "google_project_iam_member" "runner_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa["testlyn-runner"].email}"
}

resource "google_project_iam_member" "runner_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.sa["testlyn-runner"].email}"
}

resource "google_project_iam_member" "runner_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.sa["testlyn-runner"].email}"
}

resource "google_project_iam_member" "runner_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.sa["testlyn-runner"].email}"
}

resource "google_project_iam_member" "runner_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.sa["testlyn-runner"].email}"
}

# testlyn-report bindings
resource "google_project_iam_member" "report_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.sa["testlyn-report"].email}"
}

resource "google_project_iam_member" "report_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.sa["testlyn-report"].email}"
}

resource "google_project_iam_member" "report_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.sa["testlyn-report"].email}"
}

resource "google_project_iam_member" "report_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.sa["testlyn-report"].email}"
}

resource "google_project_iam_member" "report_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.sa["testlyn-report"].email}"
}

# testlyn-web bindings
resource "google_project_iam_member" "web_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.sa["testlyn-web"].email}"
}

# testlyn-chat SA + bindings removed — standalone chat Cloud Run service torn
# down (folded into testlyn-api in-process, PR #29). This state owns the SA AND
# the 5 chat_* bindings, so this apply is the DESTROYER: removing the for_each
# entry drops the SA, and the bindings are removed in the same apply (dependency-
# correct, bindings destroyed before/with the SA they reference). The infra-repo
# apps/testlyn config also declared this SA in its state — after this apply
# destroys the live SA, that side must `terraform state rm
# google_service_account.testlyn_chat` (no live SA left to destroy there).
# NOTE: chat_secret_accessor granted access TO testlyn-internal-token-dev (shared
# run-lifecycle secret) — only the chat SA's BINDING is removed, the secret stays.

# Workload Identity Federation binding for GitHub Actions CI
resource "google_project_iam_member" "github_wif_token_creator" {
  count   = var.github_wif_sa_email != "" ? 1 : 0
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${var.github_wif_sa_email}"
}
