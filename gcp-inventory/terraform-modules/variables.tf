variable "project" {
  description = "Name of the project"
  type        = string
  default     = "antiope"
}

variable "bucket_name" {
  description = "Name of bucket"
  type        = string
  default     = "code-bucket"
}

variable "function_name" {
  description = "Name of the function"
  type        = string
  default     = "main"
}

variable "topic_name" {
  description = "Name of the topic"
  type        = string
  default     = "topic-trigger"
}

variable "env" {
  description = "Name of the environment"
  type        = string
  default     = "sandbox"
}

variable "services" {
  description = "Services to be enabled"
  type        = list
  default     = ["cloudbuild.googleapis.com", "cloudfunctions.googleapis.com", "cloudresourcemanager.googleapis.com", "cloudasset.googleapis.com"]
}

variable "associated_service_account" {
  description = "Name of the app engine service account"
  type        = string
}