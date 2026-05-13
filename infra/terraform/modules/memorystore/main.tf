resource "google_redis_instance" "cache" {
  project        = var.project_id
  name           = "testlyn-redis-${var.env}"
  tier           = var.tier
  memory_size_gb = var.memory_size_gb
  region         = var.region
  redis_version  = "REDIS_7_0"

  authorized_network = var.vpc_id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }

  depends_on = [var.private_vpc_connection]
}
