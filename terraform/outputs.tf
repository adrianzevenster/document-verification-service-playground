output "assigned_roles" {
  value = local.roles
}

# GCS bucket name
output "bucket_name" {
  value = module.gcs_bucket.bucket_name
}

# DocAI Processor ID
output "processor_id" {
  value = module.documentai_processor.processor_id
}

# SA account email
output "service_account_email" {
  value = google_service_account.document_ai.email
}

# Vertex AI SA email
output "vertex_sa_email" {
  value = module.vertex_ai.vertex_sa_email
}

# Vertex AI workbench notebook instance
output "notebook_instance_name" {
  value = module.vertex_ai.notebook_instance_name
}

# Additional DocAI Processors
output "extra_processor_ids" {
  description = "Map of logical name of the repository"
  value       = { for k, m in module.extra_processors : k => m.processor_id}
}

# Gemini API key
output "gemini_api_key" {
  description = "Gemini API key"
  value       = google_apikeys_key.gemini_api_key.key_string
  sensitive   = true
}
# Training processors in DocAI SA email creation
output "trainer_sa_email" {
  value = google_service_account.trainer_sa.email
}

# Training processors in DocAI SA key creation
output "trainer_sa_key_json" {
  value   = google_service_account_key.trainer_key.private_key
  sensitive = true
  description = "base64 encoded JSON key"
}