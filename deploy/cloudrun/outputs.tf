output "vllm_url" {
  description = "vLLM service URL. OpenAI base = <url>/v1. Requires an ID token (run.invoker)."
  value       = google_cloud_run_v2_service.vllm.uri
}

output "qa_url" {
  description = "QA prompting service URL (POST /retrieve, /answer)."
  value       = var.qa_enabled ? google_cloud_run_v2_service.qa[0].uri : "(disabled — apply with -var qa_enabled=true)"
}

output "benchmark_caller_sa" {
  description = "SA tautsec-benchmarking authenticates as. Mint a key for Vercel with: gcloud iam service-accounts keys create key.json --iam-account <this>"
  value       = google_service_account.benchmark_caller.email
}

output "data_bucket" {
  description = "GCS bucket for corpus shards (shard-N) and graph-index output."
  value       = data.google_storage_bucket.data.name
}

output "image_push_command" {
  description = "Build + push the extractor image via Cloud Build (run from repo root)."
  value       = "gcloud builds submit --project ${var.project_id} --config deploy/cloudbuild/extractor.yaml --substitutions _IMAGE=${local.extractor_image} ."
}

output "qa_image_push_command" {
  description = "Build + push the QA serving image via Cloud Build (run from repo root)."
  value       = "gcloud builds submit --project ${var.project_id} --config deploy/cloudbuild/serve.yaml --substitutions _IMAGE=${local.qa_image} ."
}

output "run_extraction_command" {
  description = "Kick off a sharded extraction batch."
  value       = "gcloud run jobs execute ${google_cloud_run_v2_job.extractor.name} --region ${var.region} --project ${var.project_id}"
}

output "qa_curl_example" {
  description = "Authenticated test call (as yourself; the app uses the benchmark caller SA)."
  value       = "curl -s -H \"Authorization: Bearer $(gcloud auth print-identity-token)\" -H 'Content-Type: application/json' -d '{\"query\":\"...\",\"top_k\":5}' <qa_url>/answer"
}
