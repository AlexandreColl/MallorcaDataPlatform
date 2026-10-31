terraform {
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69.0" # patch releases only: a minor upgrade is a reviewed change of this line
    }
  }

  # Local state by default: nothing here is applied by CI. A real deployment would keep the state in S3 (with
  # native locking), see backend.tf.example.
}
