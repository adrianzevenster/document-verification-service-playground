resource "google_service_account" "documentai_sa" {
  account_id    = var.service_account_name
  display_name  = var.service_account_name
  project       = var.project_id
}

output "service_account_emial" {
  value = google_service_account.documentai_sa.email
}