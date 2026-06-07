# Infrastructure the gfmrag extractor needs (in addition to the vLLM server):
# a CPU node pool to run on, an image registry, a data bucket, and an identity.

# --- CPU node pool ----------------------------------------------------------
# The cluster removed its default pool and the GPU pool is tainted, so we need a
# general CPU pool for system workloads AND the extractor Job (which is LLM-API-
# bound, not GPU-bound — the GPU work happens in vLLM).
resource "google_container_node_pool" "cpu" {
  name     = "cpu-pool"
  cluster  = google_container_cluster.primary.id
  location = var.region

  autoscaling {
    min_node_count = 1
    max_node_count = 10
  }

  node_config {
    machine_type = var.extractor_machine_type
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    labels       = { workload = "extractor" }
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# --- Artifact Registry for the gfmrag image ---------------------------------
resource "google_artifact_registry_repository" "gfmrag" {
  location      = var.region
  repository_id = var.image_repo
  format        = "DOCKER"
  description   = "gfmrag extractor images"
}

# --- GCS bucket for corpus in + graph-index artifacts out -------------------
resource "google_storage_bucket" "data" {
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true # scaffolding convenience
}

# --- Workload Identity: pod -> GCP service account, no keys -----------------
resource "google_service_account" "extractor" {
  account_id   = "gfmrag-extractor"
  display_name = "gfmrag extractor (Workload Identity)"
}

# Let the extractor read/write the data bucket.
resource "google_storage_bucket_iam_member" "extractor_objects" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.extractor.email}"
}

# Bind the K8s SA (defined in extractor_job.tf) to the GCP SA.
resource "google_service_account_iam_member" "extractor_wi" {
  service_account_id = google_service_account.extractor.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/gfmrag-extractor]"
}
