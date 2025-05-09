resource "google_service_account" "vertex_sa" {
  account_id   = "vertex-workbench-sa"
  display_name = "Vertex Workbench Service Account"
}

resource "google_service_account" "document_ai_service_account" {
  account_id   = var.service_account_name
  display_name = "Document AI Service Account"
}