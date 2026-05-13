resource "google_sql_database_instance" "postgres" {
  project             = var.project_id
  name                = "testlyn-pg-${var.env}"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = var.env == "prod" ? true : false

  settings {
    tier              = var.db_tier
    availability_type = var.env == "prod" ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true
    disk_size         = 20

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = var.env == "prod" ? true : false
      transaction_log_retention_days = var.env == "prod" ? 7 : 1
      backup_retention_settings {
        retained_backups = var.env == "prod" ? 7 : 2
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = var.vpc_id
    }

    user_labels = {
      app        = "testlyn"
      phase      = "1"
      env        = var.env
      managed-by = "terraform"
    }

    database_flags {
      name  = "max_connections"
      value = "100"
    }
  }

  depends_on = [var.private_vpc_connection]
}

resource "google_sql_database" "testlyn" {
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
  name     = "testlyn"
}

resource "google_sql_user" "api" {
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
  name     = "testlyn_api"
  password = var.db_password
}
