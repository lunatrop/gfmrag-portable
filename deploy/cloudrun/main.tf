# Shared infrastructure for the Cloud Run variant: APIs, registries, data
# bucket, identities, and the IAM that wires callers to callees.
#
# NOTE: this stack and deploy/terraform (GKE) define the SAME bucket/registry
# names — apply one stack or the other, not both.

locals {
  extractor_image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.image_repo}/${var.image_name}:${var.image_tag}"
  qa_image        = "${var.region}-docker.pkg.dev/${var.project_id}/${var.image_repo}/${var.qa_image_name}:${var.image_tag}"

  # Cloud Run can only pull from GCP registries, so Docker Hub images (vLLM)
  # are pulled through an Artifact Registry remote (pull-through cache) repo.
  vllm_image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.dockerhub.repository_id}/vllm/vllm-openai:v0.6.6"
}

# --- APIs ---------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    # Creates the Compute Engine default SA, which Cloud Build runs as on
    # newer projects (see the IAM grants below).
    "compute.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# Cloud Build (new-project default behavior) runs builds as the Compute Engine
# default SA, which lacks registry-push and log-write rights out of the box.
data "google_project" "project" {}

resource "google_project_iam_member" "cloudbuild_ar_writer" {
  project    = var.project_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "cloudbuild_logs" {
  project    = var.project_id
  role       = "roles/logging.logWriter"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  depends_on = [google_project_service.apis]
}

# --- Artifact Registry ---------------------------------------------------------
# Built images (extractor, gfmrag-qa).
resource "google_artifact_registry_repository" "gfmrag" {
  location      = var.region
  repository_id = var.image_repo
  format        = "DOCKER"
  description   = "gfmrag extractor + QA images"
  depends_on    = [google_project_service.apis]
}

# Pull-through cache for Docker Hub (vllm/vllm-openai).
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
  depends_on = [google_project_service.apis]
}

# --- GCS bucket: corpus shards in, graph-index out ------------------------------
resource "google_storage_bucket" "data" {
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true # scaffolding convenience
}

# --- Workload identity ----------------------------------------------------------
# One runtime SA for all three gfmrag workloads (mirrors the GKE stack, where
# the QA pod reused the extractor's identity).
resource "google_service_account" "runtime" {
  account_id   = "gfmrag-runtime"
  display_name = "gfmrag Cloud Run workloads (vLLM, extractor, QA)"
}

# External caller: tautsec-benchmarking (Vercel-hosted Next.js). Its server-side
# API routes authenticate as this SA and attach an ID token per request.
resource "google_service_account" "benchmark_caller" {
  account_id   = "gfmrag-benchmark-caller"
  display_name = "tautsec-benchmarking -> gfmrag QA/vLLM caller"
}

resource "google_storage_bucket_iam_member" "runtime_objects" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

# --- HF token secret -------------------------------------------------------------
resource "google_secret_manager_secret" "hf" {
  secret_id = "gfmrag-hf-token"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "hf" {
  secret      = google_secret_manager_secret.hf.id
  secret_data = var.hf_token != "" ? var.hf_token : "unused"
}

resource "google_secret_manager_secret_iam_member" "runtime_hf" {
  secret_id = google_secret_manager_secret.hf.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
