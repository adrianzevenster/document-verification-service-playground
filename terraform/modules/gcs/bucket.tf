resource "google_storage_bucket" "docs_bucket" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = true
}

output "bucket_name" {
  value = google_storage_bucket.docs_bucket.name
}