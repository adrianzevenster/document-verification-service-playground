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

resource "google_project_iam_binding" "project_roles" {
  for_each = toset(local.roles)

  project  = var.project_id
  role     = each.key

  members  = var.members
}