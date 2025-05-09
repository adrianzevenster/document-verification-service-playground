variable "project_id" {
  description = "adg-delivery-moniepoint"
  type        = string
}

variable "location" {
  description = "GCP Region"
  type        = string
  default     = "eu"
}

variable "members" {
  description = "List of users or service accounts to bind roles to"
  type        = list(string)
}

variable "bucket_name" {
  description = "Bucket to assign to objects"
  type        = string
}

variable "processor_name" {
  description = "Docai Processor Name"
  type        = string
}

variable "processor_type" {
  description = "OCR Processor Name"
  type        = string
}

variable "service_account_name" {
  description = "service accounts"
  type        = string
}

variable "machine_type" {
  description = "machine type for Vertex AI workbench instance"
  type        = string
  default     = "n1-standard-4"
}

variable "workbench_owners" {
  description = "List of email addresses for instance owners"
  type        = list(string)
  default     = ["user:adrian@adg.io"]
}

variable "notebook_instance_name" {
  description = "Name of the Vertex AI Workbench instance"
  type        = string
  default     = "vertex-ai-workbench"
}
