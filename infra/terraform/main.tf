locals {
  name = "${var.name_prefix}-${var.environment}"
}

# Raw API responses, untouched (the MinIO `bronze` bucket). Versioned: re-running a window overwrites the object and
# the previous response stays as a noncurrent version.
module "bronze" {
  source                  = "./modules/bucket"
  name                    = "${local.name}-bronze"
  versioning              = true
  noncurrent_version_days = var.bronze_noncurrent_days
  force_destroy           = var.force_destroy
}

# Clean observations as Parquet, partitioned by source and day (the MinIO `silver` bucket): what Athena reads.
module "silver" {
  source                  = "./modules/bucket"
  name                    = "${local.name}-silver"
  versioning              = true
  noncurrent_version_days = 30
  force_destroy           = var.force_destroy
}

# Athena query results: temporary, not versioned and deleted after a few days.
module "athena_results" {
  source          = "./modules/bucket"
  name            = "${local.name}-athena-results"
  versioning      = false
  expiration_days = var.athena_results_days
  force_destroy   = true
}
