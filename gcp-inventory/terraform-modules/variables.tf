variable "project" {
  description = "Name of the project"
  type        = string
  default     = "antiope"
}

variable "organization" {
  description = "Name of the organization"
  type        = string
}

variable "cron" {
  description = "Cron schedule for the antope function"
  type        = string
  # Default is once every hour
  default     = "0 * * * *"
}

variable "archive_bucket_name" {
  description = "Name of bucket containing cloud function zip"
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
}

variable "services" {
  description = "Services to be enabled"
  type        = list
  default     = ["cloudbuild.googleapis.com", "cloudfunctions.googleapis.com", "cloudresourcemanager.googleapis.com", "cloudasset.googleapis.com", "cloudscheduler.googleapis.com", "pubsub.googleapis.com"]
}

variable "app_engine_location" {
  description = "App engine location"
  type        = string
  default     = "us-central"
}

variable "cloud_scheduler_location" {
  description = "Cloud scheduler location. Should be in same location as app engine"
  type        = string
  default     = "us-central1"
}

variable "code_location" {
  description = "Location for python code"
  type        = string
}