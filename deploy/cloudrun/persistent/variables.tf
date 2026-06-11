variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "bucket_name" {
  type        = string
  description = "Data bucket; must match the compute stack's bucket_name."
}

variable "image_repo" {
  type    = string
  default = "gfmrag"
}
