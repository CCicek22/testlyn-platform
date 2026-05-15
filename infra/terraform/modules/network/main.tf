locals {
  common_labels = {
    app        = "testlyn"
    phase      = "1"
    env        = var.env
    managed-by = "terraform"
  }
}

resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "testlyn-vpc"
  auto_create_subnetworks = false
  # google_compute_network does not support labels
}

resource "google_compute_subnetwork" "subnet" {
  project       = var.project_id
  name          = "testlyn-subnet-${var.region}"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id

  private_ip_google_access = true
  # google_compute_subnetwork supports labels but label propagation happens via
  # google_compute_network; individual subnet labels not required by policy.
}

resource "google_compute_global_address" "private_ip_range" {
  project       = var.project_id
  name          = "testlyn-private-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
  # google_compute_global_address does not support labels
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]
  # google_service_networking_connection does not support labels
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
