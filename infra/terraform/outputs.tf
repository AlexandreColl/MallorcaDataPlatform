output "bronze_bucket" {
  description = "BRONZE_BUCKET for the pipeline."
  value       = module.bronze.id
}

output "silver_bucket" {
  description = "SILVER_BUCKET for the pipeline."
  value       = module.silver.id
}

output "pipeline_role_arn" {
  description = "Role the Airflow and Spark containers assume."
  value       = aws_iam_role.pipeline.arn
}

output "analyst_role_arn" {
  description = "Read-only role for Athena."
  value       = aws_iam_role.analyst.arn
}

output "athena_workgroup" {
  description = "Workgroup to run the queries in."
  value       = aws_athena_workgroup.analytics.name
}

output "glue_database" {
  description = "Catalog database with the observations table."
  value       = aws_glue_catalog_database.silver.name
}

output "pipeline_env" {
  description = "Environment of the pipeline on AWS: real S3 instead of MinIO (credentials come from the role)."
  value = {
    S3_ENDPOINT_URL  = "https://s3.${data.aws_region.current.region}.amazonaws.com"
    S3_REGION        = data.aws_region.current.region
    S3A_INPUT_STREAM = "analytics"
    BRONZE_BUCKET    = module.bronze.id
    SILVER_BUCKET    = module.silver.id
  }
}
