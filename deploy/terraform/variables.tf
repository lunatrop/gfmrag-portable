variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region for the GKE cluster."
  default     = "us-central1"
}

variable "cluster_name" {
  type        = string
  description = "GKE cluster name."
  default     = "gfmrag-vllm"
}

# --- GPU sizing -------------------------------------------------------------
# 1x NVIDIA L4 on g2-standard-8 is the cost/throughput sweet spot for a 7B model
# served with vLLM. Bump to g2-standard-24 / multiple L4s, or A100 (a2-*) for
# larger models.
variable "gpu_machine_type" {
  type    = string
  default = "g2-standard-8"
}

variable "gpu_type" {
  type    = string
  default = "nvidia-l4"
}

variable "gpu_count" {
  type        = number
  description = "GPUs per vLLM pod / node."
  default     = 1
}

# --- Autoscaling ------------------------------------------------------------
variable "min_replicas" {
  type    = number
  default = 1
}

variable "max_replicas" {
  type    = number
  default = 6
}

# --- Model ------------------------------------------------------------------
# The open model vLLM serves. Matches the benchmarking recommendation:
# a non-thinking 7B instruct model is the hyperscale sweet spot for extraction.
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
