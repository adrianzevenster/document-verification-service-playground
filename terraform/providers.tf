provider "google" {
  project = var.project_id
  region  = var.notebook_region
}

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.34.0"
    }
  }
}
