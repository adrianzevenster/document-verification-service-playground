resource "google_document_ai_processor" "doc_processor" {
  name         = var.processor_name
  project      = var.project_id
  location     = var.location
  type         = var.processor_type
  display_name = var.processor_name
}

output "processor_id" {
  value = google_document_ai_processor.doc_processor.name
}