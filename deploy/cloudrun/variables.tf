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

# --- Extractor job -----------------------------------------------------------
variable "extractor_parallelism" {
  type        = number
  description = "Number of corpus shards = number of parallel job tasks."
  default     = 4
}

variable "extractor_cpu" {
  type    = string
  default = "4"
}

variable "extractor_memory" {
  type    = string
  default = "16Gi"
}

# Per-task ceiling. Cloud Run Jobs cap at 24h ("86400s") — size shards to fit.
variable "extractor_task_timeout" {
  type    = string
  default = "21600s"
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
  default     = "mycorpus"
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
