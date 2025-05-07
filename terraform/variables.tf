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