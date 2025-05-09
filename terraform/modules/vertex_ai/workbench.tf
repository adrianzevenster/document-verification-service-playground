resource "google_service_account" "vertex_sa" {
  account_id   = "vertex-workbench-sa"
  display_name = "Vertex Workbench Service Account"
}

resource "google_service_account_iam_binding" "vertex_sa_act_as" {
  service_account_id = google_service_account.vertex_sa.name
  role               = "roles/iam.serviceAccountUser"
  members            = [
    for email in var.workbench_owners :
    "user:${email}"
  ]
}

resource "google_notebooks_instance" "notebook_instance" {
  name            = var.notebook_instance_name
  project         = var.project_id
  location        = var.notebook_region
  machine_type    = var.machine_type
  service_account = google_service_account.vertex_sa.email

  // instead of vm_image with an unknown family, use a container that always exists:
  container_image {
    repository = "gcr.io/deeplearning-platform-release/tf2-cpu.2-13"
    tag        = "latest"
  }

  boot_disk_type    = "PD_SSD"
  boot_disk_size_gb = 100

  install_gpu_driver = false
  instance_owners    = var.workbench_owners
}


resource "google_project_iam_binding" "vertex_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/storage.objectViewer",
    "roles/notebooks.runner",
  ])
  project = var.project_id
  role    = each.value
  members = ["serviceAccount:${google_service_account.vertex_sa.email}"]
}


