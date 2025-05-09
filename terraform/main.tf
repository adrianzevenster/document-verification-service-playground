locals {
  roles = [
    "roles/documentai.apiUser",
    "roles/documentai.editor",
    "roles/aiplatform.user",
    "roles/iam.serviceAccountUser",
    "roles/storage.objectViewer",
    "roles/storage.objectCreator",
    "roles/notebooks.viewer",
    "roles/notebooks.runner",
    "roles/monitoring.viewer"
  ]
}

resource "google_service_account" "document_ai_service_account" {
  account_id   = var.service_account_name
  display_name = "${var.service_account_name} for Document AI"
}

resource "google_project_iam_binding" "service_account_permissions" {
  for_each = toset([
    "roles/documentai.apiUser",
    "roles/documentai.editor",
    "roles/aiplatform.user",
    "roles/iam.serviceAccountUser",
    "roles/storage.objectViewer",
    "roles/storage.objectCreator",
    "roles/notebooks.viewer",
    "roles/notebooks.runner",
    "roles/monitoring.viewer"
  ])

  project = var.project_id
  role    = each.value

  members = [
    "serviceAccount:${google_service_account.document_ai_service_account.email}"
  ]
}

module "documentai_processor" {
  source         = "./modules/documentai"
  project_id     = var.project_id
  location       = var.location
  processor_name = var.processor_name
  processor_type = var.processor_type
}

module "service_accounts" {
  source               = "./modules/service_accounts"
  project_id           = var.project_id
  service_account_name = var.service_account_name
}

module "vertex_ai" {
  source                = "./modules/vertex_ai"
  project_id            = var.project_id
  location              = var.location
  machine_type          = var.machine_type
  workbench_owners      = var.workbench_owners
  notebook_instance_name = var.notebook_instance_name
}


module "gcs_bucket" {
  source      = "./modules/gcs"
  bucket_name = var.bucket_name
  region      = var.location
}
