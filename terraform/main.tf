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
    "roles/monitoring.viewer",
  ]
}

# Create the Document AI SA
resource "google_service_account" "document_ai" {
  account_id   = var.service_account_name
  display_name = "${var.service_account_name} for Document AI"
}

# Grant it all the roles in locals.roles
resource "google_project_iam_binding" "docai_sa_roles" {
  for_each = toset(local.roles)
  project  = var.project_id
  role     = each.value
  members  = [
    "serviceAccount:${google_service_account.document_ai.email}"
  ]
}

# Enable the APIs
resource "google_project_service" "storage"   { service = "storage.googleapis.com"   }
resource "google_project_service" "documentai"{ service = "documentai.googleapis.com" }
resource "google_project_service" "notebooks" { service = "notebooks.googleapis.com" }

# Modules
module "documentai_processor" {
  source         = "./modules/documentai"
  project_id     = var.project_id
  location       = var.docai_location
  processor_name = var.processor_name
  processor_type = var.processor_type
}

module "gcs_bucket" {
  source      = "./modules/gcs"
  bucket_name = var.bucket_name
  region      = var.gcs_region
}

module "vertex_ai" {
  source                 = "./modules/vertex_ai"
  project_id             = var.project_id
  notebook_region        = var.notebook_region
  machine_type           = var.machine_type
  workbench_owners       = var.workbench_owners
  notebook_instance_name = var.notebook_instance_name
}

resource "google_service_account_iam_member" "allow_adrian_to_act_as_vertex_sa" {
  service_account_id = module.vertex_ai.vertex_sa_id
  role               = "roles/iam.serviceAccountUser"
  member             = "user:adrian@adg.io"
}
