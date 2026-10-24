"""SparkSession factory (local mode) and the silver DataFrame schema."""

from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql import types as T

from core.config import Settings

SILVER_SCHEMA = T.StructType(
    [
        T.StructField("source", T.StringType(), False),
        T.StructField("entity", T.StringType(), False),
        T.StructField("metric", T.StringType(), False),
        T.StructField("ts", T.TimestampType(), False),
        T.StructField("value", T.DoubleType(), True),
        T.StructField("unit", T.StringType(), False),
        T.StructField("quality", T.StringType(), False),
        T.StructField("lat", T.DoubleType(), True),
        T.StructField("lon", T.DoubleType(), True),
    ]
)


def build_spark(settings: Settings, app_name: str = "mallorca-data-platform") -> SparkSession:
    builder = (
        SparkSession.builder.appName(app_name)
        .master(settings.spark_master)
        .config("spark.driver.memory", settings.spark_driver_memory)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.ui.enabled", "false")
        # S3A -> MinIO. On AWS only the endpoint and credentials provider change.
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.endpoint", settings.s3_endpoint_url)
        .config("spark.hadoop.fs.s3a.endpoint.region", settings.s3_region)
        .config("spark.hadoop.fs.s3a.access.key", settings.s3_access_key)
        .config("spark.hadoop.fs.s3a.secret.key", settings.s3_secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.input.stream.type", settings.s3a_input_stream)
        .config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            str(settings.s3_endpoint_url.startswith("https")).lower(),
        )
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )
    )
    if settings.spark_extra_jars:
        builder = builder.config("spark.jars", settings.spark_extra_jars)
    return builder.getOrCreate()
