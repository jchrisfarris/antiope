locals {
  prepend = "${var.project}-${var.env}"
  timestamp = formatdate("YYMMDDhhmmss", timestamp())
}

data "google_billing_account" "acct" {
  display_name = "My Billing Account" # should be variablized
  open         = true
}

resource "google_project" "antiope" {
  name       = local.prepend
  project_id = "${var.project}-${random_string.unique_project_identifier.result}"
  billing_account = data.google_billing_account.acct.id
  org_id     = var.organization
}

resource "google_organization_iam_binding" "sa_binding" {
  org_id = var.organization
  role    = "roles/cloudasset.viewer"

  members = [
    "serviceAccount:${google_service_account.func_antiope.email}"
  ]
  depends_on = [google_service_account.func_antiope]
}

resource "google_service_account" "func_antiope" {
  account_id   = "${var.project}-func-antiope"
  display_name = "${var.function_name}-func-antiope"
  project      =  google_project.antiope.project_id
}

resource "google_app_engine_application" "app" {
  project     = google_project.antiope.project_id
  location_id = var.app_engine_location
}

resource "google_project_service" "gcp_services" {
  count   = length(var.services)
  service = var.services[count.index]
  depends_on = [google_project.antiope]
  disable_dependent_services = true
  project      =  google_project.antiope.project_id
}

resource "random_string" "unique_bucket_identifier" {
  length           = 8
  special          = false
  lower            = true
  upper            = false
}

resource "random_string" "unique_project_identifier" {
  length           = 8
  special          = false
  min_numeric      = 8
}

resource "google_storage_bucket" "code_source" {
  name = "${local.prepend}-${var.archive_bucket_name}-${random_string.unique_bucket_identifier.result}"
  depends_on = [google_project.antiope]
  project      =  google_project.antiope.project_id
  labels = {
    name = "${local.prepend}-${var.archive_bucket_name}"
  }
}

data "archive_file" "src" {
  type        = "zip"
  source_dir  = var.code_location
  output_path = "/tmp/function-${local.timestamp}.zip"
}

resource "google_storage_bucket_object" "archive" {
  name   = "${local.prepend}-${data.archive_file.src.output_md5}"
  bucket = google_storage_bucket.code_source.name
  source = data.archive_file.src.output_path
  depends_on = [google_project.antiope]
}

resource "google_cloudfunctions_function" "function" {
  name = "${local.prepend}-${var.function_name}"
  description = "Antiope function"
  runtime     = "python37"
  available_memory_mb   = 128
  source_archive_bucket = google_storage_bucket.code_source.name
  source_archive_object = google_storage_bucket_object.archive.name
  event_trigger {
    resource   = google_pubsub_topic.antiope.name
    event_type = "providers/cloud.pubsub/eventTypes/topic.publish"
  }
  ingress_settings      = "ALLOW_INTERNAL_ONLY"
  depends_on = [google_project_service.gcp_services, google_storage_bucket_object.archive, google_project.antiope]
  entry_point           = "main"
  service_account_email = google_service_account.func_antiope.email
  project      =  google_project.antiope.project_id
  environment_variables = {
    ORGANIZATION = var.organization
  }
}

resource "google_pubsub_topic" "antiope" {
  name = "${local.prepend}-${var.topic_name}"
  depends_on = [google_project.antiope]
  project      =  google_project.antiope.project_id
}

resource "google_cloud_scheduler_job" "job" {
  name        = "${local.prepend}-func-trigger"
  description = "Schedulde trigger for the antiope function"
  schedule    = var.cron

  pubsub_target {
    topic_name = google_pubsub_topic.antiope.id
    data       = base64encode("main")
  }
  depends_on = [google_project.antiope,google_app_engine_application.app]
  project      =  google_project.antiope.project_id
  region       = var.cloud_scheduler_location
}
