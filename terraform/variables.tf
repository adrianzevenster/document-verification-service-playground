variable "project_id" {
  description = "adg-delivery-moniepoint"
  type        = string
}

variable "region" {
  description = "eu"
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

variable "service_account_name" {
  description = "service accounts"
  type        = string
}