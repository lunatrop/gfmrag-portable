# The extraction workload as a Cloud Run Job: one parallel task per dataset in
# var.extractor_datasets — the direct analog of the GKE Indexed Job, with
# CLOUD_RUN_TASK_INDEX selecting the dataset instead of JOB_COMPLETION_INDEX
# naming the shard. Zero cost when idle.
#
# Run with:  gcloud run jobs execute gfmrag-extract --region <region>

resource "google_cloud_run_v2_job" "extractor" {
  name                = "gfmrag-extract"
  location            = var.region
  deletion_protection = false

  template {
    parallelism = length(var.extractor_datasets)
    task_count  = length(var.extractor_datasets)

    template {
      service_account = google_service_account.runtime.email
      timeout         = var.extractor_task_timeout
      max_retries     = 3

      # The image is built with --extras faiss-gpu (cloud deployments use GPU
      # faiss), so each task gets an L4: native faiss-gpu + fast ColBERT EL.
      # Each parallel task takes one GPU — size extractor_datasets against the
      # regional L4 allocation that vLLM also draws from.
      gpu_zonal_redundancy_disabled = true
      node_selector {
        accelerator = "nvidia-l4"
      }

      containers {
        image = local.extractor_image

        env {
          name  = "VLLM_URL"
          value = google_cloud_run_v2_service.vllm.uri
        }

        # Read models (ColBERT etc.) from the shared cache — anonymous HF
        # downloads from shared Cloud Run egress IPs get 429-rate-limited.
        env {
          name  = "HF_HOME"
          value = "/models/hf"
        }

        # Task N extracts the N-th dataset of this list.
        env {
          name  = "DATASETS"
          value = join(",", var.extractor_datasets)
        }

        # Cloud Run enforces IAM per request, so the OpenAI client's bearer
        # token must be a Google ID token for the vLLM service. Fetched from
        # the metadata server at task start.
        #
        # CAVEAT: ID tokens expire after 1h. For shards that extract longer
        # than that, add a token-refresh hook to gfmrag's OpenAI client (or
        # split into smaller shards).
        command = ["/bin/sh", "-c"]
        args = [
          <<-EOT
          export OPENAI_BASE_URL="$${VLLM_URL}/v1"
          export OPENAI_API_KEY=$(curl -s -H 'Metadata-Flavor: Google' \
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=$${VLLM_URL}")
          DATA_NAME=$(echo "$${DATASETS}" | cut -d, -f$(($${CLOUD_RUN_TASK_INDEX} + 1)))
          echo "task $${CLOUD_RUN_TASK_INDEX} -> dataset $${DATA_NAME}"
          python -m gfmrag.workflow.index_dataset \
            dataset.root=/data \
            dataset.data_name=$${DATA_NAME} \
            openie_model.llm_api=openai \
            openie_model.model_name=${var.model_id} \
            openie_model.max_triples_tokens=6000 \
            ner_model.llm_api=openai \
            ner_model.model_name=${var.model_id}
          EOT
        ]

        resources {
          limits = {
            cpu              = var.extractor_cpu
            memory           = var.extractor_memory
            "nvidia.com/gpu" = "1"
          }
        }

        volume_mounts {
          name       = "data"
          mount_path = "/data"
        }

        volume_mounts {
          name       = "hf-cache"
          mount_path = "/models/hf"
        }
      }

      # Built-in GCS volume mount — replaces the GKE GCS FUSE CSI driver.
      volumes {
        name = "data"
        gcs {
          bucket    = google_storage_bucket.data.name
          read_only = false
        }
      }

      volumes {
        name = "hf-cache"
        gcs {
          bucket    = google_storage_bucket.hf_cache.name
          read_only = false # uncached models populate on first use
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}
