# QA prompting service over the knowledge graph — the endpoint
# tautsec-benchmarking calls (/retrieve, /answer). Gated behind var.qa_enabled
# (default false) until extraction has written the KG index to GCS.
#
# Enable with: terraform apply -var qa_enabled=true

resource "google_cloud_run_v2_service" "qa" {
  count = var.qa_enabled ? 1 : 0

  name                = "gfmrag-qa"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  # Model + index load is slow even with a warm cache.
  timeouts {
    create = "45m"
    update = "45m"
  }

  template {
    service_account = google_service_account.runtime.email

    # GPU-bound per request (embeddings + ColBERT EL); keep concurrency low.
    max_instance_request_concurrency = 4

    scaling {
      min_instance_count = 0
      max_instance_count = var.qa_max_instances
    }

    gpu_zonal_redundancy_disabled = true
    node_selector {
      accelerator = "nvidia-l4"
    }

    containers {
      image = local.qa_image

      ports {
        container_port = 8000
      }

      env {
        name  = "DATA_DIR"
        value = "/data"
      }
      env {
        name  = "DATA_NAME"
        value = var.qa_data_name
      }
      env {
        name  = "GFM_MODEL_PATH"
        value = var.gfm_model_path
      }
      env {
        name  = "LLM_API"
        value = "openai"
      }
      env {
        name  = "LLM_MODEL"
        value = var.model_id
      }
      env {
        name  = "OPENAI_BASE_URL"
        value = "${google_cloud_run_v2_service.vllm.uri}/v1"
      }
      # Placeholder only: with VLLM_AUDIENCE set, app.py overrides this with
      # ID tokens minted from the metadata server (vLLM sits behind IAM).
      env {
        name  = "OPENAI_API_KEY"
        value = "dummy"
      }
      env {
        name  = "VLLM_AUDIENCE"
        value = google_cloud_run_v2_service.vllm.uri
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

      # Checkpoint + 16GB embedding model (FUSE reads) + possible stage-2
      # rebuild: typical ~7 min, worst observed >20 — allow 35.
      startup_probe {
        http_get {
          path = "/healthz"
          port = 8000
        }
        period_seconds    = 15
        timeout_seconds   = 5
        failure_threshold = 140
      }

      volume_mounts {
        name       = "index"
        mount_path = "/data"
      }

      volume_mounts {
        name       = "hf-cache"
        mount_path = "/models/hf" # = HF_HOME (Dockerfile.serve)
      }
    }

    # Read-write: from_index WRITES processed/stage2 (graph.pt + embeddings)
    # back to the bucket — persisted, so later starts skip the rebuild.
    volumes {
      name = "index"
      gcs {
        bucket    = data.google_storage_bucket.data.name
        read_only = false
      }
    }

    # De-ephemeralised HF weights (Qwen3-Embedding-8B etc.) — populated on
    # first start, read intra-region afterwards.
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

# Only tautsec-benchmarking calls this from outside.
resource "google_cloud_run_v2_service_iam_member" "qa_invoker_benchmark" {
  count = var.qa_enabled ? 1 : 0

  name     = google_cloud_run_v2_service.qa[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.benchmark_caller.email}"
}

resource "google_cloud_run_v2_service_iam_member" "qa_extra_invokers" {
  for_each = var.qa_enabled ? toset(var.extra_invoker_members) : toset([])

  name     = google_cloud_run_v2_service.qa[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = each.value
}
