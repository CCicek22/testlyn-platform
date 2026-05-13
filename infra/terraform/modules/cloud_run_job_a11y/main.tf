locals {
  common_labels = {
    app        = "testlyn"
    phase      = "2"
    env        = var.env
    managed-by = "terraform"
    product    = "a11y"
  }
}

resource "google_cloud_run_v2_job" "engine_a11y" {
  project  = var.project_id
  name     = "testlyn-engine-a11y"
  location = var.region

  labels = local.common_labels

  template {
    labels = local.common_labels

    parallelism = 1
    task_count  = 1

    template {
      service_account       = var.service_account_email
      timeout               = "${var.timeout_seconds}s"
      max_retries           = var.max_retries
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

      vpc_access {
        connector = var.vpc_connector_id
        egress    = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = var.image

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        dynamic "env" {
          for_each = var.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = var.secret_env_vars
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value.secret
                version = env.value.version
              }
            }
          }
        }
      }
    }
  }
}
