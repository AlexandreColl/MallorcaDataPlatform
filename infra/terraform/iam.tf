# Two roles with the least privilege each one needs:
# - pipeline: what the Airflow/Spark containers do (write raw responses to bronze, overwrite silver partitions);
# - analyst: read-only SQL through Athena (silver and the catalog, its own results), never the raw bronze.

locals {
  trusted_arns = length(var.pipeline_trusted_arns) > 0 ? var.pipeline_trusted_arns : [
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root",
  ]
  glue_catalog_arns = [
    "arn:aws:glue:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:catalog",
    aws_glue_catalog_database.silver.arn,
    "arn:aws:glue:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.silver.name}/*",
  ]
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = local.trusted_arns
    }
  }
}

# --------------------------------------------------------------------------------------------------- pipeline

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid       = "ListLakeBuckets"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [module.bronze.arn, module.silver.arn]
  }

  # Bronze is append and overwrite only: the pipeline never deletes a raw response (versioning keeps old ones).
  statement {
    sid       = "ReadWriteBronze"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${module.bronze.arn}/*"]
  }

  # Spark's dynamic partition overwrite deletes the files of the partitions it rewrites.
  statement {
    sid = "ReadWriteSilver"
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts",
    ]
    resources = ["${module.silver.arn}/*"]
  }
}

resource "aws_iam_role" "pipeline" {
  name                 = "${local.name}-pipeline"
  description          = "Airflow and Spark: write bronze and silver."
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "pipeline" {
  name   = "lake-read-write"
  role   = aws_iam_role.pipeline.id
  policy = data.aws_iam_policy_document.pipeline.json
}

# --------------------------------------------------------------------------------------------------- analyst

data "aws_iam_policy_document" "analyst" {
  statement {
    sid = "QueryWithAthena"
    actions = [
      "athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution",
      "athena:GetWorkGroup", "athena:ListNamedQueries", "athena:GetNamedQuery",
    ]
    resources = [aws_athena_workgroup.analytics.arn]
  }

  statement {
    sid       = "ReadCatalog"
    actions   = ["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"]
    resources = local.glue_catalog_arns
  }

  statement {
    sid       = "ReadSilver"
    actions   = ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = [module.silver.arn, "${module.silver.arn}/*"]
  }

  statement {
    sid       = "OwnQueryResults"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:AbortMultipartUpload"]
    resources = [module.athena_results.arn, "${module.athena_results.arn}/*"]
  }
}

resource "aws_iam_role" "analyst" {
  name                 = "${local.name}-analyst"
  description          = "Read-only SQL over silver through Athena."
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "analyst" {
  name   = "athena-read-only"
  role   = aws_iam_role.analyst.id
  policy = data.aws_iam_policy_document.analyst.json
}
