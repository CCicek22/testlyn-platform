resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "testlyn-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  project       = var.project_id
  name          = "testlyn-subnet-${var.region}"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id

  private_ip_google_access = true
}

resource "google_compute_global_address" "private_ip_range" {
  project       = var.project_id
  name          = "testlyn-private-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]
}

resource "google_vpc_access_connector" "connector" {
  project        = var.project_id
  name           = "testlyn-vpc-connector"
  region         = var.region
  network        = google_compute_network.vpc.name
  ip_cidr_range  = var.connector_cidr
  min_throughput = 200
  max_throughput = 1000
}
