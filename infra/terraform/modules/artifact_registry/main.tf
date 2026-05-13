resource "google_artifact_registry_repository" "testlyn" {
  project       = var.project_id
  location      = var.region
  repository_id = "testlyn"
  description   = "Testlyn container images"
  format        = "DOCKER"

  labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }
}
