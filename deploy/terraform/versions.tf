terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }

  # For real use, store state remotely (uncomment and set your bucket):
  # backend "gcs" {
  #   bucket = "my-tfstate-bucket"
  #   prefix = "gfmrag/vllm"
  # }
}
