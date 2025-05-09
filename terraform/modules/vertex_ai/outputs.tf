output "vertex_sa_email" {
  value = google_service_account.vertex_sa.email
}

output "notebook_instance_name" {
  value = google_notebooks_instance.notebook_instance.name
}
