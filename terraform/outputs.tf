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
  value = google_service_account.document_ai.email
}
output "vertex_sa_email" {
  value = module.vertex_ai.vertex_sa_email
}
output "notebook_instance_name" {
  value = module.vertex_ai.notebook_instance_name
}

output "extra_processor_ids" {
  description = "Map of logical name of the repository"
  value       = { for k, m in module.extra_processors : k => m.processor_id}
}
