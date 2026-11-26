"""The silver DataFrame: its schema, its lineage columns, the quality labels and one row per key.

Shared by the local pipeline (``core/pipeline.py``) and the Databricks job (``databricks/``). It imports PySpark and
the quality engine only, never MinIO, boto3 or Postgres, so it runs as is on Databricks serverless compute.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from core.models import KEY
from core.quality import QualityEngine, rules_for

if TYPE_CHECKING:
    from datetime import datetime

    from pyspark.sql import DataFrame, SparkSession

    from core.connectors import BaseConnector
    from core.models import Observation, TimeWindow
    from core.quality import RuleResult

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


def to_dataframe(spark: SparkSession, observations: list[Observation], run_id: str) -> DataFrame:
    """Build the silver DataFrame with lineage columns (`run_id`, `ingested_at`)."""
    rows = [o.as_row() for o in observations]
    df = spark.createDataFrame(rows, schema=SILVER_SCHEMA)
    return df.withColumn("run_id", F.lit(run_id)).withColumn("ingested_at", F.current_timestamp())


def deduplicate(df: DataFrame) -> DataFrame:
    """Keep one row per key; prefer a non-null value."""
    w = Window.partitionBy(*KEY).orderBy(F.col("value").isNull().asc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def apply_quality(
    df: DataFrame, connector: BaseConnector, window: TimeWindow, span: tuple[datetime, datetime] | None = None
) -> tuple[DataFrame, list[RuleResult]]:
    """Label rows with the connector's rule set, then collapse duplicates.

    ``span`` narrows the time steps the gaps rule expects to the part of the window the source could cover.
    """
    flagged, results = QualityEngine(rules_for(connector.config, window, span)).run(df)
    return deduplicate(flagged), results
