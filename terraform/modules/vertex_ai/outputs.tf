output "vertex_sa_email" {
  value = google_service_account.vertex_sa.email
}

output "notebook_instance_name" {
  value = google_notebooks_instance.notebook_instance.name
}
output "vertex_sa_id" {
  description = "The full resource name of the vertex-workbench-sa service account"
  value       = google_service_account.vertex_sa.id
}
