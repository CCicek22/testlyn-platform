output "key_name" {
  description = "Fully-qualified KMS CryptoKey resource name in use."
  value       = local.effective_key
}

output "key_ring_name" {
  description = "KMS key ring name (empty when BYOK key was provided)."
  value       = local.create_key ? google_kms_key_ring.testlyn[0].name : ""
}
