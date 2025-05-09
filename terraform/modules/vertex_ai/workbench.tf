resource "google_service_account" "vertex_sa" {
  account_id   = "vertex-workbench-sa"
  display_name = "Vertex Workbench Service Account"
}

resource "google_notebooks_instance" "notebook_instance" {
  name            = var.notebook_instance_name
  project         = var.project_id
  location        = var.location
  machine_type    = var.machine_type
  service_account = google_service_account.vertex_sa.email

  # Pick one image type: VM
  vm_image {
    project      = "deeplearning-platform-release"
    image_family = "tf2-ent-2-13-cpu"
  }

  boot_disk_type    = "PD_SSD"
  boot_disk_size_gb = 100

  install_gpu_driver    = false
  instance_owners       = var.workbench_owners
}

resource "google_project_iam_binding" "vertex_sa_roles" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  members = ["serviceAccount:${google_service_account.vertex_sa.email}"]
}

resource "google_project_iam_binding" "vertex_sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  members = ["serviceAccount:${google_service_account.vertex_sa.email}"]
}

resource "google_project_iam_binding" "vertex_sa_runner" {
  project = var.project_id
  role    = "roles/notebooks.runner"
  members = ["serviceAccount:${google_service_account.vertex_sa.email}"]
}
