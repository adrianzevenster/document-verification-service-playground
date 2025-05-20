# Project ID
variable "project_id" {
  type        = string
  description = "GCP project ID"
}

# Members to bind to SA
variable "members" {
  type        = list(string)
  description = "Users / service-accounts to bind to our roles"
}

# SA account name
variable "service_account_name" {
  type        = string
  description = "Base name for the Document AI service account"
}

# GCS bucket name for Images and PDFs
variable "bucket_name" {
  type        = string
  description = "Name of the GCS bucket"
}

# DocAI processor name
variable "processor_name" {
  type        = string
  description = "Document AI processor display name"
}

# DocAI processor type
variable "processor_type" {
  type        = string
  description = "Document AI processor type, e.g. OCR_PROCESSOR"
}

# Variables for different processor
variable "additional_processors" {
  description = <<EOT
  Key-value map of extra Document AI processor to create
  Key = logical name
  Value = Exact Processor Type
EOT
  type        = map(string)
  default     = {
    form_parser = "FORM_PARSER_PROCESSOR"
    utility_parser = "UTILITY_PROCESSOR"
    custom_classifier = "CUSTOM_CLASSIFICATION_PROCESSOR"
    custom_extractor = "CUSTOM_EXTRACTION_PROCESSOR"
    layout_processor = "LAYOUT_PARSER_PROCESSOR"
  }
}

# DocAI region
variable "docai_location" {
  type        = string
  description = "Location for Document AI (e.g. eu or us)"
}

# GCS region
variable "gcs_region" {
  type        = string
  description = "Region for the GCS bucket (e.g. EU)"
}

# Workbench notebook region
variable "notebook_region" {
  type        = string
  description = "Zone for the Vertex AI Workbench (e.g. europe-west1-b)"
}

# Vertex AI workbench notebook name
variable "notebook_instance_name" {
  type        = string
  description = "Name of the Vertex AI Workbench instance"
}

# Vertex AI workbench notebook machine type
variable "machine_type" {
  type        = string
  default     = "n1-standard-4"
  description = "Machine type for the Notebook VM"
}

# Accounts that own notebook instance
variable "workbench_owners" {
  type        = list(string)
  default     = ["user:adrian@adg.io"]
  description = "Who can access the Notebook"
}

# Account that can act as SA on vertex workbench
variable "vertex_sa_actors" {
  type        = list(string)
  description = "Principals allowed to act as the vertex workbench sa"
  default     = ["adrian@adg.io"]
}

# DocAI SA account to allow interfacing with processors
variable "trainer_sa_name" {
  type        = string
  default     = "my-documentai-sa"
  description = "Trainer service account"
}