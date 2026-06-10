# The extraction workload as a Cloud Run Job: N parallel tasks, one corpus
# shard each — the direct analog of the GKE Indexed Job, sharded by
# CLOUD_RUN_TASK_INDEX instead of JOB_COMPLETION_INDEX. Zero cost when idle.
#
# Run with:  gcloud run jobs execute gfmrag-extract --region <region>

resource "google_cloud_run_v2_job" "extractor" {
  name                = "gfmrag-extract"
  location            = var.region
  deletion_protection = false

  template {
    parallelism = var.extractor_parallelism
    task_count  = var.extractor_parallelism

    template {
      service_account = google_service_account.runtime.email
      timeout         = var.extractor_task_timeout
      max_retries     = 3

      containers {
        image = local.extractor_image

        env {
          name  = "VLLM_URL"
          value = google_cloud_run_v2_service.vllm.uri
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
          python -m gfmrag.workflow.index_dataset \
            dataset.root=/data \
            dataset.data_name=shard-$${CLOUD_RUN_TASK_INDEX} \
            openie_model.llm_api=openai \
            openie_model.model_name=${var.model_id} \
            ner_model.llm_api=openai \
            ner_model.model_name=${var.model_id}
          EOT
        ]

        resources {
          limits = {
            cpu    = var.extractor_cpu
            memory = var.extractor_memory
          }
        }

        volume_mounts {
          name       = "data"
          mount_path = "/data"
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
    }
  }

  depends_on = [google_project_service.apis]
}
