output "vpc_id" {
  description = "VPC network self-link"
  value       = google_compute_network.vpc.id
}

output "vpc_name" {
  description = "VPC network name"
  value       = google_compute_network.vpc.name
}

output "subnet_id" {
  description = "Subnet self-link"
  value       = google_compute_subnetwork.subnet.id
}

output "connector_id" {
  description = "VPC Access Connector self-link"
  value       = google_vpc_access_connector.connector.id
}

output "private_vpc_connection" {
  description = "Private VPC connection for Cloud SQL"
  value       = google_service_networking_connection.private_vpc_connection.id
}
