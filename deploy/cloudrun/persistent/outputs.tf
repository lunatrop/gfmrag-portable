output "data_bucket" {
  value = google_storage_bucket.data.name
}

output "hf_cache_bucket" {
  value = google_storage_bucket.hf_cache.name
}

output "image_repo" {
  value = google_artifact_registry_repository.gfmrag.repository_id
}

output "dockerhub_repo" {
  value = google_artifact_registry_repository.dockerhub.repository_id
}
