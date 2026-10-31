# Least privilege: the pipeline writes the lake but never deletes raw responses; the analyst only reads silver
# through Athena and never sees bronze.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "eu-south-2" }
  }
  # The provider validates policy JSON: the rendered documents are a minimal valid policy (the tests assert on the
  # statements themselves).
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

run "pipeline_role" {
  command = apply

  assert {
    condition = toset(one([
      for s in data.aws_iam_policy_document.pipeline.statement : s.actions if s.sid == "ReadWriteBronze"
    ])) == toset(["s3:GetObject", "s3:PutObject"])
    error_message = "bronze is read and written, never deleted"
  }
  assert {
    condition = toset(one([
      for s in data.aws_iam_policy_document.pipeline.statement : s.resources if s.sid == "ReadWriteBronze"
    ])) == toset(["${module.bronze.arn}/*"])
    error_message = "bronze access is limited to its objects"
  }
  assert {
    condition = contains(one([
      for s in data.aws_iam_policy_document.pipeline.statement : s.actions if s.sid == "ReadWriteSilver"
    ]), "s3:DeleteObject")
    error_message = "the dynamic partition overwrite of Spark needs to delete silver files"
  }
  assert {
    condition = alltrue(flatten([
      for s in data.aws_iam_policy_document.pipeline.statement : [for a in s.actions : !strcontains(a, "*")]
    ]))
    error_message = "no wildcard actions"
  }
  assert {
    condition = !contains(flatten([
      for s in data.aws_iam_policy_document.pipeline.statement : s.resources
    ]), "*")
    error_message = "no wildcard resources"
  }
}

run "analyst_role" {
  command = apply

  assert {
    condition = !anytrue(flatten([
      for s in data.aws_iam_policy_document.analyst.statement : [for r in s.resources : strcontains(r, module.bronze.arn)]
    ]))
    error_message = "the analyst never reads bronze"
  }
  assert {
    condition = alltrue(flatten([
      for s in data.aws_iam_policy_document.analyst.statement : [for a in s.actions : !contains(["s3:DeleteObject", "glue:CreateTable", "glue:DeleteTable", "glue:UpdateTable"], a)]
    ]))
    error_message = "the analyst cannot delete data or change the catalog"
  }
  assert {
    condition = toset(one([
      for s in data.aws_iam_policy_document.analyst.statement : s.actions if s.sid == "ReadSilver"
    ])) == toset(["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"])
    error_message = "silver is read only"
  }
  assert {
    condition = one([
      for s in data.aws_iam_policy_document.analyst.statement : s.resources if s.sid == "QueryWithAthena"
    ]) == toset([aws_athena_workgroup.analytics.arn])
    error_message = "queries only run in the project workgroup"
  }
}

run "roles_trust_the_account_by_default" {
  command = apply

  assert {
    condition = one(one(data.aws_iam_policy_document.assume.statement).principals).identifiers == toset([
      "arn:aws:iam::123456789012:root",
    ])
    error_message = "without trusted ARNs the roles trust the account (its IAM policies decide who assumes them)"
  }
}

run "roles_trust_the_given_principals" {
  command = apply

  variables {
    pipeline_trusted_arns = ["arn:aws:iam::123456789012:role/airflow-task"]
  }

  assert {
    condition = one(one(data.aws_iam_policy_document.assume.statement).principals).identifiers == toset([
      "arn:aws:iam::123456789012:role/airflow-task",
    ])
    error_message = "the trusted principals replace the account"
  }
}
