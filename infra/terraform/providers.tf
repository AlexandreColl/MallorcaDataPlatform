provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "mallorca-data-platform"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repository  = "github.com/AlexandreColl/MallorcaDataPlatform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
