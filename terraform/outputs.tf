output "assigned_roles" {
  value = local.roles
}

output "bucket_name" {
  value = module.gcs_bucket.bucket_name
}

output "processor_id" {
  value = module.documentai_processor.processor_id
}

output "service_account_email" {
  value = module.service_accounts.document_ai_service_account_email
}

output "vertex_sa_email" {
  value = module.service_accounts.vertex_sa_email
}

output "notebook_instance_name" {
  value = module.vertex_ai.notebook_instance_name
}
