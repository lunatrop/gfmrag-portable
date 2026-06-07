# Online prompting service over the knowledge graph. Loads the GFM checkpoint
# (8M / 34M) + the KG index from GCS (read-only), and serves /retrieve + /answer.
# Query-NER and answer generation call the in-cluster vLLM.

# HF token secret in the default namespace (GFM-RAG-8M + Qwen3-Embedding are
# public, so this is only needed if you point at gated weights).
resource "kubernetes_secret_v1" "hf_default" {
  metadata {
    name      = "hf-token"
    namespace = "default"
  }
  data = { token = var.hf_token }
  type = "Opaque"
}

resource "kubernetes_deployment_v1" "qa" {
  metadata {
    name      = "gfmrag-qa"
    namespace = "default"
    labels    = { app = "gfmrag-qa" }
  }

  spec {
    replicas = var.qa_min_replicas

    selector {
      match_labels = { app = "gfmrag-qa" }
    }

    template {
      metadata {
        labels      = { app = "gfmrag-qa" }
        annotations = { "gke-gcsfuse/volumes" = "true" }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.extractor.metadata[0].name

        # Embeddings (Qwen3-Embedding-8B) + ColBERT EL need a GPU; the GNN is tiny.
        # Runs on the GPU pool. Give it its OWN GPU — raise the GPU pool's
        # max_node_count (or add a dedicated pool) so it doesn't contend with vLLM.
        node_selector = { "cloud.google.com/gke-accelerator" = var.gpu_type }
        toleration {
          key      = "nvidia.com/gpu"
          operator = "Equal"
          value    = "present"
          effect   = "NoSchedule"
        }

        container {
          name  = "qa"
          image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.image_repo}/${var.qa_image_name}:${var.image_tag}"

          port {
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
            value = "http://vllm.llm.svc.cluster.local/v1"
          }
          env {
            name  = "OPENAI_API_KEY"
            value = "dummy"
          }
          env {
            name = "HUGGING_FACE_HUB_TOKEN"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.hf_default.metadata[0].name
                key  = "token"
              }
            }
          }

          resources {
            requests = {
              cpu    = "2"
              memory = "16Gi"
            }
            limits = {
              "nvidia.com/gpu" = "1"
              memory           = "24Gi"
            }
          }

          # Model + index load is slow; gate traffic until /healthz is ok.
          readiness_probe {
            http_get {
              path = "/healthz"
              port = 8000
            }
            initial_delay_seconds = 300
            period_seconds        = 15
            failure_threshold     = 40
          }

          volume_mount {
            name       = "index"
            mount_path = "/data"
            read_only  = true
          }
        }

        volume {
          name = "index"
          csi {
            driver    = "gcsfuse.csi.storage.gke.io"
            read_only = true
            volume_attributes = {
              bucketName   = google_storage_bucket.data.name
              mountOptions = "implicit-dirs,read_only"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "qa" {
  metadata {
    name      = "gfmrag-qa"
    namespace = "default"
    annotations = {
      "networking.gke.io/load-balancer-type" = "Internal"
    }
  }
  spec {
    selector = { app = "gfmrag-qa" }
    port {
      port        = 80
      target_port = 8000
    }
    type = "LoadBalancer"
  }
}

resource "kubernetes_horizontal_pod_autoscaler_v2" "qa" {
  metadata {
    name      = "gfmrag-qa"
    namespace = "default"
  }
  spec {
    min_replicas = var.qa_min_replicas
    max_replicas = var.qa_max_replicas

    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.qa.metadata[0].name
    }

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 65
        }
      }
    }
  }
}
