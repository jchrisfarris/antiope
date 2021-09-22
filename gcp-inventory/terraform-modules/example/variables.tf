variable "organization" {
  description = "Organization associated with this deployment"
  type        = string
}

variable "env" {
  description = "Environment for the deployment"
  type        = string
}

variable "code_location" {
  description = "Location for python code"
  type        = string
}