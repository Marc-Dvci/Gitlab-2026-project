terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0"
    }
  }
  backend "http" {} # GitLab-managed Terraform state (free); configured by the configure:infra CI job
}

provider "google" {
  project = var.project_id
  region  = var.region
}
