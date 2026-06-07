# Variables for the extractor image, storage, and Job.

variable "image_repo" {
  type        = string
  description = "Artifact Registry repository id."
  default     = "gfmrag"
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
  description = "GCS bucket for corpus input + graph-index output. Must be globally unique."
}

variable "extractor_machine_type" {
  type    = string
  default = "e2-standard-4"
}

variable "extractor_parallelism" {
  type        = number
  description = "Number of parallel extractor pods = number of corpus shards."
  default     = 4
}

variable "extractor_cpu" {
  type    = string
  default = "2"
}

variable "extractor_memory" {
  type    = string
  default = "8Gi"
}
