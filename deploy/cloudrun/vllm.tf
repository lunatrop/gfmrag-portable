# vLLM serving as a scale-to-zero Cloud Run GPU service. OpenAI-compatible API
# on /v1, same image and args as the GKE variant — minus the HPA (Cloud Run
# scales on request concurrency, which is the right signal for LLM serving)
# and minus the manual kubectl-scale-to-zero dance (min_instance_count = 0).
#
# Auth: no allUsers. Ingress is open (callers include Vercel, outside any VPC)
# but every request must carry an ID token from an SA with run.invoker.

resource "google_cloud_run_v2_service" "vllm" {
  name                = "gfmrag-vllm"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false # scaffolding only — set true in production

  # First-population cold starts can exceed the provider's 20m default.
  timeouts {
    create = "45m"
    update = "45m"
  }

  template {
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = var.vllm_concurrency

    scaling {
      min_instance_count = 0
      max_instance_count = var.vllm_max_instances
    }

    # 1x L4 — same cost/throughput sweet spot as the GKE node pool. Zonal
    # redundancy off = the cheaper GPU tier (fine for scaffolding).
    gpu_zonal_redundancy_disabled = true
    node_selector {
      accelerator = "nvidia-l4"
    }

    containers {
      image = local.vllm_image

      args = [
        "--model", var.model_id,
        "--max-model-len", tostring(var.max_model_len),
        "--gpu-memory-utilization", "0.92",
        "--guided-decoding-backend", "outlines",
      ]

      ports {
        container_port = 8000
      }

      env {
        name = "HUGGING_FACE_HUB_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.hf.secret_id
            version = "latest"
          }
        }
      }

      # De-ephemeralised model weights: cache on GCS instead of re-downloading
      # ~GBs from huggingface.co on every cold start. Also keeps weights out
      # of the RAM-backed filesystem (frees the 32GiB cap for bigger models).
      env {
        name  = "HF_HOME"
        value = "/models/hf"
      }

      # The cache is pre-populated (deploy/cloudbuild/prepopulate-hf-cache.yaml);
      # offline mode skips hub etag checks and guarantees no runtime downloads
      # ever crawl through the FUSE write path again.
      env {
        name  = "HF_HUB_OFFLINE"
        value = "1"
      }

      volume_mounts {
        name       = "hf-cache"
        mount_path = "/models/hf"
      }

      resources {
        limits = {
          cpu              = "8"
          memory           = "32Gi"
          "nvidia.com/gpu" = "1"
        }
        startup_cpu_boost = true
      }

      # Cold start = image pull + loading weights (GCS cache after first
      # start). Allow up to ~20 min before declaring the instance dead.
      startup_probe {
        http_get {
          path = "/health"
          port = 8000
        }
        period_seconds    = 15
        timeout_seconds   = 5
        failure_threshold = 80
      }
    }

    volumes {
      name = "hf-cache"
      gcs {
        bucket    = data.google_storage_bucket.hf_cache.name
        read_only = false
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.runtime_hf,
  ]
}

# Approved callers only: the gfmrag workloads (extractor job, QA service) and
# the tautsec-benchmarking app.
resource "google_cloud_run_v2_service_iam_member" "vllm_invokers" {
  for_each = {
    runtime   = google_service_account.runtime.email
    benchmark = google_service_account.benchmark_caller.email
  }
  name     = google_cloud_run_v2_service.vllm.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"
}

resource "google_cloud_run_v2_service_iam_member" "vllm_extra_invokers" {
  for_each = toset(var.extra_invoker_members)
  name     = google_cloud_run_v2_service.vllm.name
  location = var.region
  role     = "roles/run.invoker"
  member   = each.value
}
