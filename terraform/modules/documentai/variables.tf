variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "location" {
  description = "GCP Region for the Document AI processor"
  type        = string
}

variable "processor_name" {
  description = "Document AI Processor Name"
  type        = string
}

variable "processor_type" {
  description = "Document AI Processor Type"
  type        = string
}
