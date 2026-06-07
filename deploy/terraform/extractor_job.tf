# The extraction workload itself: an Indexed Job that shards a corpus across N
# parallel pods. Each pod runs `gfmrag.workflow.index_dataset` (NER + OpenIE),
# pointing the LLM at the in-cluster vLLM service and reading/writing GCS.

# K8s SA annotated for Workload Identity (bound to the GCP SA in extractor_infra.tf).
resource "kubernetes_service_account_v1" "extractor" {
  metadata {
    name      = "gfmrag-extractor"
    namespace = "default"
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.extractor.email
    }
  }
}

resource "kubernetes_job_v1" "extractor" {
  metadata {
    name      = "gfmrag-extract"
    namespace = "default"
  }

  spec {
    # Indexed Job: pods get JOB_COMPLETION_INDEX 0..N-1 -> one corpus shard each.
    completion_mode = "Indexed"
    completions     = var.extractor_parallelism
    parallelism     = var.extractor_parallelism
    backoff_limit   = 4

    template {
      metadata {
        labels = { app = "gfmrag-extract" }
        annotations = {
          "gke-gcsfuse/volumes" = "true"
        }
      }
      spec {
        service_account_name = kubernetes_service_account_v1.extractor.metadata[0].name
        restart_policy       = "Never"
        node_selector        = { workload = "extractor" }

        container {
          name  = "extractor"
          image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.image_repo}/${var.image_name}:${var.image_tag}"

          # Point the OpenIE/NER backend at the in-cluster vLLM (OpenAI API).
          # Use the Service DNS, not the LB IP — no egress, lower latency.
          env {
            name  = "OPENAI_BASE_URL"
            value = "http://vllm.llm.svc.cluster.local/v1"
          }
          env {
            name  = "OPENAI_API_KEY"
            value = "dummy" # vLLM ignores unless started with --api-key
          }

          # Shard by the Indexed-Job completion index. Assumes the corpus was
          # pre-split into data/shard-0, shard-1, ... under the bucket.
          command = ["/bin/sh", "-c"]
          args = [
            <<-EOT
            python -m gfmrag.workflow.index_dataset \
              dataset.root=/data \
              dataset.data_name=shard-$${JOB_COMPLETION_INDEX} \
              openie_model.llm_api=openai \
              openie_model.model_name=${var.model_id} \
              ner_model.llm_api=openai \
              ner_model.model_name=${var.model_id}
            EOT
          ]

          resources {
            requests = {
              cpu    = var.extractor_cpu
              memory = var.extractor_memory
            }
            limits = {
              cpu    = var.extractor_cpu
              memory = var.extractor_memory
            }
          }

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }
        }

        # Mount the GCS bucket as a filesystem via the GCS FUSE CSI driver.
        volume {
          name = "data"
          csi {
            driver = "gcsfuse.csi.storage.gke.io"
            volume_attributes = {
              bucketName   = google_storage_bucket.data.name
              mountOptions = "implicit-dirs"
            }
          }
        }
      }
    }
  }

  wait_for_completion = false
}
