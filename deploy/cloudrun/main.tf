# Compute stack for the Cloud Run variant: services, job, identities, secrets,
# and the IAM that wires callers to callees. The long-lived artifacts (data +
# hf_cache buckets, Artifact Registry repos) live in persistent/ and are read
# here via data sources, so `terraform destroy` of THIS stack never touches
# them. Apply order: persistent/ first, then here.
#
# NOTE: this stack and deploy/terraform (GKE) define the SAME bucket/registry
# names — apply one stack or the other, not both.

# --- Persistent artifacts (created by persistent/, read-only here) ------------
data "google_storage_bucket" "data" {
  name = var.bucket_name
}

data "google_storage_bucket" "hf_cache" {
  name = "${var.bucket_name}-hf-cache"
}

data "google_artifact_registry_repository" "gfmrag" {
  location      = var.region
  repository_id = var.image_repo
}

data "google_artifact_registry_repository" "dockerhub" {
  location      = var.region
  repository_id = "dockerhub"
}

locals {
  extractor_image = "${var.region}-docker.pkg.dev/${var.project_id}/${data.google_artifact_registry_repository.gfmrag.repository_id}/${var.image_name}:${var.image_tag}"
  qa_image        = "${var.region}-docker.pkg.dev/${var.project_id}/${data.google_artifact_registry_repository.gfmrag.repository_id}/${var.qa_image_name}:${var.image_tag}"

  # Cloud Run can only pull from GCP registries, so Docker Hub images (vLLM)
  # are pulled through an Artifact Registry remote (pull-through cache) repo.
  vllm_image = "${var.region}-docker.pkg.dev/${var.project_id}/${data.google_artifact_registry_repository.dockerhub.repository_id}/vllm/vllm-openai:v0.6.6"
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

resource "google_storage_bucket_iam_member" "runtime_hf_cache" {
  bucket = data.google_storage_bucket.hf_cache.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

# Automation fallback: the gfmrag-terraform SA runs jobs when user CLI creds
# hit the org's reauth wall (SA keys have no session expiry).
resource "google_project_iam_member" "terraform_sa_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:gfmrag-terraform@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "terraform_sa_builds" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:gfmrag-terraform@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "terraform_sa_logs" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:gfmrag-terraform@${var.project_id}.iam.gserviceaccount.com"
}

# builds submit stages the source tarball here.
resource "google_storage_bucket_iam_member" "terraform_sa_build_source" {
  bucket = "${var.project_id}_cloudbuild"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:gfmrag-terraform@${var.project_id}.iam.gserviceaccount.com"
}

# Cloud Build pre-populates the cache (deploy/cloudbuild/prepopulate-hf-cache.yaml)
# — writing weights through GCS FUSE from an instance is ~1MB/s; this is minutes.
resource "google_storage_bucket_iam_member" "cloudbuild_hf_cache" {
  bucket = data.google_storage_bucket.hf_cache.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
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
  bucket = data.google_storage_bucket.data.name
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
