# The buckets: private, encrypted, TLS only, versioned where the data must survive a re-run, temporary where not.
# Every test runs against a mocked AWS provider: no account, no credentials, no cost.

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

run "buckets_are_named_per_environment" {
  command = apply

  assert {
    condition     = output.bronze_bucket == "mallorca-data-platform-dev-bronze"
    error_message = "bronze bucket name"
  }
  assert {
    condition     = output.silver_bucket == "mallorca-data-platform-dev-silver"
    error_message = "silver bucket name"
  }
  assert {
    condition     = module.athena_results.id == "mallorca-data-platform-dev-athena-results"
    error_message = "athena results bucket name"
  }
}

run "bucket_module_defaults" {
  command = apply

  module {
    source = "./modules/bucket"
  }

  variables {
    name = "mdp-test-bucket"
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.this.block_public_acls,
      aws_s3_bucket_public_access_block.this.block_public_policy,
      aws_s3_bucket_public_access_block.this.ignore_public_acls,
      aws_s3_bucket_public_access_block.this.restrict_public_buckets,
    ])
    error_message = "public access must be fully blocked"
  }
  assert {
    condition     = aws_s3_bucket_ownership_controls.this.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled"
  }
  assert {
    condition     = one([for r in aws_s3_bucket_server_side_encryption_configuration.this.rule : one(r.apply_server_side_encryption_by_default).sse_algorithm]) == "AES256"
    error_message = "objects must be encrypted with SSE-S3"
  }
  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled"
    error_message = "versioning is on by default"
  }
  assert {
    condition     = one(one(data.aws_iam_policy_document.tls_only.statement).condition).values == tolist(["false"])
    error_message = "the bucket policy must deny requests without TLS"
  }
  assert {
    condition     = one(data.aws_iam_policy_document.tls_only.statement).effect == "Deny"
    error_message = "the TLS statement is a Deny"
  }
  assert {
    condition     = contains([for r in aws_s3_bucket_lifecycle_configuration.this.rule : r.id], "expire-old-versions")
    error_message = "old versions expire"
  }
  assert {
    condition     = !contains([for r in aws_s3_bucket_lifecycle_configuration.this.rule : r.id], "expire-objects")
    error_message = "current objects never expire by default"
  }
}

run "temporary_bucket_expires_objects_and_has_no_versions" {
  command = apply

  module {
    source = "./modules/bucket"
  }

  variables {
    name            = "mdp-test-results"
    versioning      = false
    expiration_days = 7
  }

  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Suspended"
    error_message = "a temporary bucket is not versioned"
  }
  assert {
    condition = one([
      for r in aws_s3_bucket_lifecycle_configuration.this.rule : one(r.expiration).days if r.id == "expire-objects"
    ]) == 7
    error_message = "objects expire after 7 days"
  }
  assert {
    condition     = !contains([for r in aws_s3_bucket_lifecycle_configuration.this.rule : r.id], "expire-old-versions")
    error_message = "no version rule without versioning"
  }
}

run "bucket_names_are_validated" {
  command = plan

  module {
    source = "./modules/bucket"
  }

  variables {
    name = "Not_A_Valid_Bucket"
  }

  expect_failures = [var.name]
}
