# The Glue table is the Delta table Spark writes, Athena is capped, and the budget alerts only when someone listens.

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

run "table_is_the_spark_delta_table" {
  command = apply

  assert {
    condition     = aws_glue_catalog_database.silver.name == "mallorca_data_platform_dev_silver"
    error_message = "Glue names use underscores"
  }
  assert {
    condition     = aws_glue_catalog_table.observations.parameters["table_type"] == "DELTA"
    error_message = "Athena reads the Delta log, not every Parquet file under the location"
  }
  assert {
    condition     = one(aws_glue_catalog_table.observations.storage_descriptor).location == "s3://mallorca-data-platform-dev-silver/observations/"
    error_message = "the table points at the directory Spark writes (core/lake.py)"
  }
  assert {
    condition     = length(aws_glue_catalog_table.observations.partition_keys) == 0
    error_message = "partitions come from the Delta log: Glue partitions would be ignored"
  }
  assert {
    condition = [for c in one(aws_glue_catalog_table.observations.storage_descriptor).columns : c.name] == [
      "source", "entity", "metric", "ts", "value", "unit", "quality", "lat", "lon", "date",
    ]
    error_message = "columns follow SILVER_SCHEMA plus the date partition"
  }
}

run "athena_is_capped_and_uses_its_bucket" {
  command = apply

  assert {
    condition     = one(aws_athena_workgroup.analytics.configuration).enforce_workgroup_configuration
    error_message = "users cannot override the workgroup settings"
  }
  assert {
    condition     = one(aws_athena_workgroup.analytics.configuration).bytes_scanned_cutoff_per_query == 1073741824
    error_message = "each query scans at most 1 GB"
  }
  assert {
    condition     = one(one(aws_athena_workgroup.analytics.configuration).result_configuration).output_location == "s3://mallorca-data-platform-dev-athena-results/"
    error_message = "results go to the temporary bucket"
  }
}

run "budget_without_emails_has_no_alerts" {
  command = apply

  assert {
    condition     = aws_budgets_budget.monthly.limit_amount == "2.00"
    error_message = "2 USD a month by default"
  }
  assert {
    condition     = length(aws_budgets_budget.monthly.notification) == 0
    error_message = "no subscribers, no notifications"
  }
}

run "budget_alerts_at_80_and_forecast_100" {
  command = apply

  variables {
    budget_alert_emails = ["owner@example.com"]
    monthly_budget_usd  = 5
  }

  assert {
    condition     = aws_budgets_budget.monthly.limit_amount == "5.00"
    error_message = "the limit follows the variable"
  }
  assert {
    condition = toset([for n in aws_budgets_budget.monthly.notification : "${n.notification_type}:${n.threshold}"]) == toset([
      "ACTUAL:80", "FORECASTED:100",
    ])
    error_message = "an alert at 80 % spent and one at 100 % forecast"
  }
}

run "invalid_inputs_are_rejected" {
  command = plan

  variables {
    environment        = "staging"
    monthly_budget_usd = 0
  }

  expect_failures = [var.environment, var.monthly_budget_usd]
}
