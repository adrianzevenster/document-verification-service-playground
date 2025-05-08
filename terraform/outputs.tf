output "assigned_roles" {
  value = local.roles
}

output "bound_members" {
  value = var.members
}

output "bucket_name" {
  value = module.gcs_bucket.bucket_name
}

output "processor_id" {
  value = module.documentai_processor.processor_id
}

output "service_account_email" {
  value = module.service_accounts.service_account_email
}