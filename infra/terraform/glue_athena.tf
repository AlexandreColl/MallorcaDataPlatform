# The silver lake as a SQL table, with no database server: the Glue Data Catalog describes the Parquet files and
# Athena queries them, paying only for the bytes it scans.
#
# Spark writes `silver/observations/source=<connector>/date=<yyyy-MM-dd>/part-*.parquet`. Partition projection tells
# Athena those values, so no crawler (billed per run) and no `MSCK REPAIR TABLE` is needed when a day lands.

resource "aws_glue_catalog_database" "silver" {
  name        = replace("${local.name}_silver", "-", "_")
  description = "Mallorca Data Platform silver layer: clean observations in the common schema."
}

resource "aws_glue_catalog_table" "observations" {
  name          = "observations"
  database_name = aws_glue_catalog_database.silver.name
  description   = "One row per source, entity, metric and hour (or day), with its quality label."
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                        = "TRUE"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.source.type"        = "enum"
    "projection.source.values"      = join(",", var.sources)
    "projection.date.type"          = "date"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.range"         = "${var.history_start},NOW"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${module.silver.id}/observations/source=$${source}/date=$${date}"
  }

  partition_keys {
    name = "source"
    type = "string"
  }

  partition_keys {
    name = "date"
    type = "date"
  }

  storage_descriptor {
    location      = "s3://${module.silver.id}/observations/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    # Same columns as SILVER_SCHEMA in core/spark.py (source is the partition, not a column of the files).
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
    { name = "entity", type = "string", comment = "Station, point or area" },
    { name = "metric", type = "string", comment = "Canonical metric name" },
    { name = "ts", type = "timestamp", comment = "UTC" },
    { name = "value", type = "double", comment = "Null when missing" },
    { name = "unit", type = "string", comment = "Canonical unit" },
    { name = "quality", type = "string", comment = "ok, suspect or missing" },
    { name = "lat", type = "double", comment = "" },
    { name = "lon", type = "double", comment = "" },
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
  description = "Partition pruning on date keeps the scan to a week of files."
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
