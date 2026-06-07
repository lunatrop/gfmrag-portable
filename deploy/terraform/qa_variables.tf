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

variable "qa_min_replicas" {
  type    = number
  default = 1
}

variable "qa_max_replicas" {
  type    = number
  default = 4
}
