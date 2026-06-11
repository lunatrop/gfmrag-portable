# Persistent artifacts for the gfmrag Cloud Run deployment.
#
# These survive `terraform destroy` of the compute stack (../). Apply once;
# rarely touched. The compute stack reads them via data sources. Guards:
#   - force_destroy = false : a destroy won't wipe a non-empty bucket
#   - prevent_destroy       : terraform refuses to destroy these at all
# Closes the old footgun where the compute stack's force_destroy=true buckets
# were silently wiped by any `terraform destroy`.
#
# Rebuild cost if lost: data bucket = shard re-upload + stage-2 rebuild;
# hf_cache = ~7min Cloud Build prepopulate; AR = 2x ~18min image builds.

resource "google_storage_bucket" "data" {
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket" "hf_cache" {
  name                        = "${var.bucket_name}-hf-cache"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle {
    prevent_destroy = true
  }
}

# Built images (extractor, gfmrag-qa).
resource "google_artifact_registry_repository" "gfmrag" {
  location      = var.region
  repository_id = var.image_repo
  format        = "DOCKER"
  description   = "gfmrag extractor + QA images"

  lifecycle {
    prevent_destroy = true
  }
}

# Pull-through cache for Docker Hub (vllm/vllm-openai) — Cloud Run can't pull
# from Docker Hub directly. Persisting it avoids Docker Hub rate-limits on
# recreate (hit twice during initial bring-up).
resource "google_artifact_registry_repository" "dockerhub" {
  location      = var.region
  repository_id = "dockerhub"
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  description   = "Docker Hub proxy (Cloud Run cannot pull from Docker Hub directly)"

  remote_repository_config {
    docker_repository {
      public_repository = "DOCKER_HUB"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
