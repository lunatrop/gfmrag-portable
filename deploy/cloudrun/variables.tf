variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Region for all Cloud Run services/jobs. Must offer L4 GPUs on Cloud Run."
  default     = "us-central1"
}

# --- Model -------------------------------------------------------------------
variable "model_id" {
  type    = string
  default = "Qwen/Qwen2.5-7B-Instruct"
}

variable "max_model_len" {
  type    = number
  default = 8192
}

# Hugging Face token (only needed for gated models). Keep out of VCS.
variable "hf_token" {
  type      = string
  sensitive = true
  default   = ""
}

# --- vLLM serving ------------------------------------------------------------
variable "vllm_max_instances" {
  type    = number
  default = 6
}

# Requests batched per instance before Cloud Run scales out. This replaces the
# GKE stack's CPU-based HPA placeholder with the right signal for LLM serving.
variable "vllm_concurrency" {
  type    = number
  default = 32
}

# --- Images / data -----------------------------------------------------------
variable "image_repo" {
  type    = string
  default = "gfmrag"
}

variable "image_name" {
  type    = string
  default = "extractor"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "bucket_name" {
  type        = string
  description = "GCS bucket for corpus shards in and graph-index out. Globally unique."
}

# Extra IAM members granted run.invoker on the services, e.g. developers
# smoke-testing with `gcloud auth print-identity-token`. Full member syntax
# ("user:dev@example.com").
variable "extra_invoker_members" {
  type    = list(string)
  default = []
}

# --- Extractor job -----------------------------------------------------------
# Dataset subdirectories under the bucket to extract — one parallel job task
# each. Pick rungs from corpus-shards/ (e.g. ["shard-0"] or
# ["shard-0", "shard-1", "shard-2"]), or ["corpus"] for the whole register
# uploaded as a single dataset.
variable "extractor_datasets" {
  type    = list(string)
  default = ["shard-0"]
  validation {
    condition     = length(var.extractor_datasets) > 0
    error_message = "extractor_datasets must name at least one dataset."
  }
}

variable "extractor_cpu" {
  type    = string
  default = "4"
}

variable "extractor_memory" {
  type    = string
  default = "16Gi"
}

# Per-task ceiling. GPU job tasks cap at 1h ("3600s") — which also matches the
# ID-token lifetime the task's vLLM auth depends on. Size shards to fit.
variable "extractor_task_timeout" {
  type    = string
  default = "3600s"
}

# --- QA prompting service (deferred by default) -------------------------------
variable "qa_enabled" {
  type        = bool
  description = "Deploy the QA prompting service. Flip on once the KG index is in GCS."
  default     = false
}

variable "qa_image_name" {
  type    = string
  default = "gfmrag-qa"
}

variable "qa_data_name" {
  type        = string
  description = "Dataset subdirectory (under the bucket) whose index to serve."
  default     = "shard-0"
}

variable "gfm_model_path" {
  type        = string
  description = "GFM checkpoint: rmanluo/GFM-RAG-8M, or the 34M G-Reasoner."
  default     = "rmanluo/GFM-RAG-8M"
}

variable "qa_max_instances" {
  type    = number
  default = 4
}
