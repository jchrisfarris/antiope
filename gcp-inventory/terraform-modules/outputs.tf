output "bucket_name" {
    value = google_storage_bucket.bucket.name
    description = "The name of the bucket"
}

output "google_storage_bucket_object_name" {
    value = google_storage_bucket_object.archive.name
    description = "The name of the object object"
}