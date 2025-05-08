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
  "roles/monitoring.viewer"]
}

module "gcs_bucket" {
  source      = "./modules/gcs"
  bucket_name = var.bucket_name
}

module "documentai_processor" {
  source         = "./modules/documentai"
  project_id     = var.project_id
  location       = var.region
  processor_name = var.processor_name
}

module "service_accounts" {
  source               = "./modules/service_accounts"
  project_id           = var.project_id
  service_account_name = var.service_account_name
}

resource "google_project_iam_binding" "project_roles" {
  for_each = toset(local.roles)

  project  = var.project_id
  role     = each.key

  members  = var.members
}

