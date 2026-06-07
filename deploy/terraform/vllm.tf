# vLLM serving stack: namespace, HF-token secret, Deployment, Service, HPA.
# vLLM exposes an OpenAI-compatible API on :8000 (/v1/chat/completions), so the
# gfmrag extractor can target it with llm_api=openai + OPENAI_BASE_URL.

resource "kubernetes_namespace_v1" "llm" {
  metadata {
    name = "llm"
  }
}

resource "kubernetes_secret_v1" "hf" {
  metadata {
    name      = "hf-token"
    namespace = kubernetes_namespace_v1.llm.metadata[0].name
  }
  data = {
    token = var.hf_token
  }
  type = "Opaque"
}

resource "kubernetes_deployment_v1" "vllm" {
  metadata {
    name      = "vllm"
    namespace = kubernetes_namespace_v1.llm.metadata[0].name
    labels    = { app = "vllm" }
  }

  spec {
    replicas = var.min_replicas

    selector {
      match_labels = { app = "vllm" }
    }

    template {
      metadata {
        labels = { app = "vllm" }
      }

      spec {
        node_selector = {
          "cloud.google.com/gke-accelerator" = var.gpu_type
        }

        toleration {
          key      = "nvidia.com/gpu"
          operator = "Equal"
          value    = "present"
          effect   = "NoSchedule"
        }

        container {
          name  = "vllm"
          image = "vllm/vllm-openai:v0.6.6"

          # Continuous batching + paged attention => high throughput.
          # guided-decoding lets callers force valid JSON (schema-constrained),
          # which eliminates the bare-list / malformed-JSON parsing failures.
          args = [
            "--model", var.model_id,
            "--max-model-len", tostring(var.max_model_len),
            "--gpu-memory-utilization", "0.92",
            "--guided-decoding-backend", "outlines",
          ]

          port {
            container_port = 8000
          }

          env {
            name = "HUGGING_FACE_HUB_TOKEN"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.hf.metadata[0].name
                key  = "token"
              }
            }
          }

          resources {
            limits = {
              "nvidia.com/gpu" = tostring(var.gpu_count)
            }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 120
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "vllm" {
  metadata {
    name      = "vllm"
    namespace = kubernetes_namespace_v1.llm.metadata[0].name
    annotations = {
      # Internal LB — keep the endpoint private to your VPC. Front with
      # API Gateway / IAP for external, authenticated access.
      "networking.gke.io/load-balancer-type" = "Internal"
    }
  }
  spec {
    selector = { app = "vllm" }
    port {
      port        = 80
      target_port = 8000
    }
    type = "LoadBalancer"
  }
}

resource "kubernetes_horizontal_pod_autoscaler_v2" "vllm" {
  metadata {
    name      = "vllm"
    namespace = kubernetes_namespace_v1.llm.metadata[0].name
  }
  spec {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.vllm.metadata[0].name
    }

    # Placeholder metric. For real LLM autoscaling, scale on queue depth
    # (vllm:num_requests_waiting) via Prometheus Adapter / custom metrics,
    # not CPU — GPU inference is rarely CPU-bound.
    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 60
        }
      }
    }
  }
}
