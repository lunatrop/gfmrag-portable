output "vllm_internal_ip" {
  description = "Internal LB IP of the vLLM service. Point gfmrag's OPENAI_BASE_URL at http://<ip>/v1"
  value       = try(kubernetes_service_v1.vllm.status[0].load_balancer[0].ingress[0].ip, "(pending — re-run `terraform output` after the LB provisions)")
}

output "vllm_openai_base_url" {
  description = "OpenAI-compatible base URL for the extractor's openai backend."
  value       = try("http://${kubernetes_service_v1.vllm.status[0].load_balancer[0].ingress[0].ip}/v1", "(pending)")
}

output "served_model_id" {
  description = "Model name to pass as gfmrag model_name when using the vLLM backend."
  value       = var.model_id
}

output "get_credentials_command" {
  description = "Run this to point kubectl at the cluster."
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${var.region} --project ${var.project_id}"
}

output "data_bucket" {
  description = "GCS bucket for corpus shards (data/shard-N) and graph-index output."
  value       = google_storage_bucket.data.name
}

output "image_push_command" {
  description = "Build + push the extractor image (run from repo root)."
  value       = "gcloud builds submit --tag ${var.region}-docker.pkg.dev/${var.project_id}/${var.image_repo}/${var.image_name}:${var.image_tag} -f deploy/docker/Dockerfile ."
}

output "qa_image_push_command" {
  description = "Build + push the prompting-service image (run from repo root)."
  value       = "gcloud builds submit --tag ${var.region}-docker.pkg.dev/${var.project_id}/${var.image_repo}/${var.qa_image_name}:${var.image_tag} -f deploy/docker/Dockerfile.serve ."
}

output "qa_service_internal_ip" {
  description = "Internal LB IP of the prompting service. POST /retrieve or /answer."
  value       = try(kubernetes_service_v1.qa.status[0].load_balancer[0].ingress[0].ip, "(pending)")
}

output "qa_curl_example" {
  description = "Example call once the service IP is assigned."
  value       = "curl -s http://<qa-ip>/answer -H 'Content-Type: application/json' -d '{\"query\":\"...\",\"top_k\":5}'"
}

