locals {
  prepend = "${var.project}-${var.env}"
}

resource "google_project_service" "gcp_services" {
  count   = length(var.services)
  project = "antiope"
  service = var.services[count.index]

  disable_dependent_services = false
}

resource "random_string" "random" {
  length           = 8
  special          = false
  lower            = true
  upper            = false
}

resource "google_storage_bucket" "bucket" {
  name = "${local.prepend}-${var.bucket_name}-${random_string.random.result}"
  labels = {
    name = "${local.prepend}-${var.bucket_name}"
  }
}

data "archive_file" "src" {
  type        = "zip"
  source_dir  = "../python_code"
  output_path = "../generated/src.zip"
}

resource "google_storage_bucket_object" "archive" {
  name   = "${local.prepend}-${var.bucket_name}-archive"
  bucket = google_storage_bucket.bucket.name
  source = "../generated/src.zip"
}

resource "google_cloudfunctions_function" "function" {
  name = "${local.prepend}-${var.function_name}"
  description = "Antiope function"
  runtime     = "python37"
  available_memory_mb   = 128
  source_archive_bucket = google_storage_bucket.bucket.name
  source_archive_object = google_storage_bucket_object.archive.name
  event_trigger {
    resource   = google_pubsub_topic.antiope.name
    event_type = "providers/cloud.pubsub/eventTypes/topic.publish"
  }
  ingress_settings      = "ALLOW_INTERNAL_ONLY"
  depends_on = [google_project_service.gcp_services, google_storage_bucket_object.archive]
  entry_point           = "main"
  service_account_email = var.associated_service_account
}

resource "google_pubsub_topic" "antiope" {
  name = "${local.prepend}-${var.topic_name}"
}
