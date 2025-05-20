locals {
  roles = [
    "roles/documentai.apiUser",
    "roles/documentai.editor",
    "roles/documentai.admin",
    "roles/aiplatform.user",
    "roles/iam.serviceAccountUser",
    "roles/storage.objectViewer",
    "roles/storage.objectCreator",
    "roles/notebooks.viewer",
    "roles/notebooks.runner",
    "roles/monitoring.viewer",
  ]
}

# roles to enable
locals {
  trainer_roles = [
  "roles/documentai.admin",
  "roles/storage.objectViewer",
  ]
}

# SA to train processors in DocAI
resource "google_service_account" "trainer_sa" {
  account_id   = var.trainer_sa_name
  display_name = "Document AI Trainer for KYC DVS"
  description = "Runs training scripts for KYC DVS entity extraction"
}

# SA binding to train processors in DocAI
resource "google_project_iam_member" "trainer_bindings" {
  for_each = toset(local.trainer_roles)

  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.trainer_sa.email}"
}

resource "time_static" "initial" {
  # No args, captures then stays
}
# Service account key to interface with DocAI processors
resource "google_service_account_key" "trainer_key" {
  service_account_id = google_service_account.trainer_sa.name
  keepers            = {
    created          = time_static.initial.id
  }
}
# Create the Document AI SA
resource "google_service_account" "document_ai" {
  account_id   = var.service_account_name
  display_name = "${var.service_account_name} for Document AI (KYC)"
}


resource "google_service_account_iam_member" "docai_key_admins" {
  for_each = toset(var.workbench_owners)

  service_account_id = google_service_account.document_ai.name
  role               = "roles/iam.serviceAccountKeyAdmin"
  member             = "user:${each.value}"
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

# Defining Document AI processors
module "extra_processors" {
  for_each = var.additional_processors
  source     = "./modules/documentai"
  project_id = var.project_id
  location   = var.docai_location
  processor_name = replace(each.key, "_", "-")
  processor_type = each.value
}

# Importing GCS bucket module
module "gcs_bucket" {
  source      = "./modules/gcs"
  bucket_name = var.bucket_name
  region      = var.gcs_region
}

# Importing vertex_ai module: Workbench, and Gemini
module "vertex_ai" {
  source                 = "./modules/vertex_ai"
  project_id             = var.project_id
  notebook_region        = var.notebook_region
  machine_type           = var.machine_type
  workbench_owners       = var.workbench_owners
  notebook_instance_name = var.notebook_instance_name
}

# Service account binding to create workbench instance
resource "google_service_account_iam_member" "allow_actors_act_as_vertex_sa" {
  for_each           = toset(var.vertex_sa_actors)

  service_account_id = module.vertex_ai.vertex_sa_id
  role               = "roles/iam.serviceAccountUser"
  member             = "user:${each.key}"

}

# Allowing for service account to act on DocAI processors
resource "google_project_iam_member" "vertex_sa_docai_editor" {
  project = var.project_id
  role    = "roles/documentai.editor"
  member  = "serviceAccount:${module.vertex_ai.vertex_sa_email}"

  depends_on = [
    google_project_iam_binding.docai_sa_roles
  ]

}

# Enable Vertex AI Gemini API
resource "google_project_service" "gemini" {
  service = "generativelanguage.googleapis.com"
}

# Gemini API Key Creation for KYC document verification
resource "google_apikeys_key" "gemini_api_key" {
  display_name = "Gemini API Key for KYC DVS entity extraction"
  name         = "kyc-dvs-gemini-api-key"

  restrictions {
    api_targets {
      service = "generativelanguage.googleapis.com"
      methods       = ["*"]
    }
  }
}