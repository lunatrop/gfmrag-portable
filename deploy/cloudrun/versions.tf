terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.30"
    }
  }

  # Recommended before shared use: GCS remote state.
  # backend "gcs" {
  #   bucket = "tautsec-graph-crawler-tfstate"
  #   prefix = "gfmrag/cloudrun"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
