output "document_ai_service_account_email" {
  value = google_service_account.document_ai_service_account.email
}

output "vertex_sa_email" {
  value = google_service_account.vertex_sa.email
}
