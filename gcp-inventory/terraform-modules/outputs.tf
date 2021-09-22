output "google_storage_bucket_name" {
    value = google_storage_bucket.code_source.name
    description = "The name of the bucket containing the source code"
}
