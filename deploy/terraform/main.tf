provider "google" {
  project = var.project_id
  region  = var.region
}

# --- GKE cluster ------------------------------------------------------------
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.region

  # Manage node pools separately (best practice).
  remove_default_node_pool = true
  initial_node_count       = 1

  networking_mode = "VPC_NATIVE"
  ip_allocation_policy {}

  # Workload Identity so pods can use GCS / Artifact Registry without keys.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Mount GCS buckets into the extractor pods as volumes.
  addons_config {
    gcs_fuse_csi_driver_config {
      enabled = true
    }
  }

  # Scaffolding only — set true in production.
  deletion_protection = false
}

# --- GPU node pool (autoscaled) --------------------------------------------
resource "google_container_node_pool" "gpu" {
  name     = "vllm-gpu-pool"
  cluster  = google_container_cluster.primary.id
  location = var.region

  autoscaling {
    min_node_count = var.min_replicas
    max_node_count = var.max_replicas
  }

  node_config {
    machine_type = var.gpu_machine_type
    image_type   = "COS_CONTAINERD"
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    guest_accelerator {
      type  = var.gpu_type
      count = var.gpu_count

      # Let GKE install/manage the NVIDIA driver.
      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }

    labels = { workload = "vllm" }

    # Keep non-GPU workloads off these expensive nodes.
    taint {
      key    = "nvidia.com/gpu"
      value  = "present"
      effect = "NO_SCHEDULE"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# --- Kubernetes provider, authenticated against the new cluster -------------
data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.primary.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
}
