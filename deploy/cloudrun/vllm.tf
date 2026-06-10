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

      resources {
        limits = {
          cpu              = "8"
          memory           = "32Gi"
          "nvidia.com/gpu" = "1"
        }
        startup_cpu_boost = true
      }

      # Cold start = image pull + downloading/loading the 7B model: minutes.
      # Allow up to ~20 min before declaring the instance dead. To cut this,
      # bake the weights into a custom image or mount them from GCS.
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
