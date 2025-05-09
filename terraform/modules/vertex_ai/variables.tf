variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "location" {
  description = "GCP location for the Notebook instance"
  type        = string
}

variable "machine_type" {
  description = "Machine type for the Notebook instance"
  type        = string
}

variable "workbench_owners" {
  description = "List of notebook owners"
  type        = list(string)
}

variable "notebook_instance_name" {
  description = "The name to give the Notebook instance"
  type        = string
}
