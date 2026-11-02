# The silver lake as a SQL table, with no database server: the Glue Data Catalog points at the Delta table and
# Athena queries it, paying only for the bytes it scans.
#
# Spark keeps `silver/observations` as a Delta Lake table: Parquet files under `source=<connector>`, ordered by time,
# plus the `_delta_log` that says which files are current. Athena (engine 3) reads that log natively: only the location
# and `table_type = DELTA` are needed. Partitions and the min/max statistics of each file (to skip files on `date` and
# `ts`) come from the log, so there is no crawler (billed per run), no `MSCK REPAIR TABLE`, and files that a MERGE
# replaced (still on S3 until VACUUM) never reach the results.

resource "aws_glue_catalog_database" "silver" {
  name        = replace("${local.name}_silver", "-", "_")
  description = "Mallorca Data Platform silver layer: clean observations in the common schema."
}

resource "aws_glue_catalog_table" "observations" {
  name          = "observations"
  database_name = aws_glue_catalog_database.silver.name
  description   = "One row per source, entity, metric and hour (or day), with its quality label (Delta Lake)."
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                     = "TRUE"
    table_type                   = "DELTA"
    "spark.sql.sources.provider" = "delta"
  }

  storage_descriptor {
    location = "s3://${module.silver.id}/observations/"

    # Documentation for the catalog: Athena takes the schema from the Delta log (SILVER_SCHEMA in core/spark.py).
    dynamic "columns" {
      for_each = local.silver_columns
      content {
        name    = columns.value.name
        type    = columns.value.type
        comment = columns.value.comment
      }
    }
  }
}

locals {
  silver_columns = [
    { name = "source", type = "string", comment = "Connector (partition)" },
    { name = "entity", type = "string", comment = "Station, point or area" },
    { name = "metric", type = "string", comment = "Canonical metric name" },
    { name = "ts", type = "timestamp", comment = "UTC" },
    { name = "value", type = "double", comment = "Null when missing" },
    { name = "unit", type = "string", comment = "Canonical unit" },
    { name = "quality", type = "string", comment = "ok, suspect or missing" },
    { name = "lat", type = "double", comment = "" },
    { name = "lon", type = "double", comment = "" },
    { name = "date", type = "date", comment = "Day of ts (file skipping through the Delta statistics)" },
  ]
}

resource "aws_athena_workgroup" "analytics" {
  name          = local.name
  description   = "Queries over the silver lake. Results expire with their bucket; each query is capped in bytes."
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = "s3://${module.athena_results.id}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# A first query to try, visible in the Athena console under "Saved queries".
resource "aws_athena_named_query" "daily_means" {
  name        = "Daily mean per source and metric (last 7 days)"
  description = "The date statistics of the Delta log keep the scan to the files of the last week."
  workgroup   = aws_athena_workgroup.analytics.id
  database    = aws_glue_catalog_database.silver.name
  query       = <<-SQL
    SELECT source, metric, date, round(avg(value), 2) AS mean_value, count(*) AS n
    FROM observations
    WHERE date >= current_date - INTERVAL '7' DAY AND quality <> 'missing'
    GROUP BY source, metric, date
    ORDER BY source, metric, date
  SQL
}
