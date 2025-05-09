variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "members" {
  type        = list(string)
  description = "Users / service-accounts to bind to our roles"
}

variable "service_account_name" {
  type        = string
  description = "Base name for the Document AI service account"
}

variable "bucket_name" {
  type        = string
  description = "Name of the GCS bucket"
}

variable "processor_name" {
  type        = string
  description = "Document AI processor display name"
}

variable "processor_type" {
  type        = string
  description = "Document AI processor type, e.g. OCR_PROCESSOR"
}

variable "docai_location" {
  type        = string
  description = "Location for Document AI (e.g. eu or us)"
}

variable "gcs_region" {
  type        = string
  description = "Region for the GCS bucket (e.g. EU)"
}

variable "notebook_region" {
  type        = string
  description = "Zone for the Vertex AI Workbench (e.g. europe-west1-b)"
}

variable "notebook_instance_name" {
  type        = string
  description = "Name of the Vertex AI Workbench instance"
}

variable "machine_type" {
  type        = string
  default     = "n1-standard-4"
  description = "Machine type for the Notebook VM"
}

variable "workbench_owners" {
  type        = list(string)
  default     = ["user:adrian@adg.io"]
  description = "Who can access the Notebook"
}
