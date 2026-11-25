"""Bronze table: Auto Loader picks up the new payload.json files of the raw volume and appends one row per file.

Auto Loader (the ``cloudFiles`` stream source) remembers in its checkpoint which files it already read, so each run
only reads what the extract tasks wrote since the last one. Serverless compute only runs streams that stop on their
own, hence ``availableNow``: read everything new, then stop. ``allowOverwrites`` makes a re-fetched window (same key,
new content) count as a new file, as bucket versioning keeps it in MinIO.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyspark.sql import functions as F

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

    from mdp_databricks.catalog import Names

log = logging.getLogger(__name__)

# The request metadata of a payload.json (core.models.RawPayload.to_json); the body stays as text in `payload`.
PAYLOAD_METADATA = (
    "source STRING, dataset STRING, `window` STRUCT<`start`: STRING, `end`: STRING>, "
    "`partition` STRING, fetched_at STRING"
)


def payload_rows(files: DataFrame) -> DataFrame:
    """Bronze rows from whole-file text rows (``value``) with Auto Loader's ``_metadata`` column."""
    meta = F.from_json("value", PAYLOAD_METADATA)
    return files.select(
        meta["source"].alias("source"),
        meta["dataset"].alias("dataset"),
        F.to_date(meta["window"]["start"]).alias("window_start"),
        F.to_date(meta["window"]["end"]).alias("window_end"),
        meta["partition"].alias("payload_partition"),
        F.to_timestamp(meta["fetched_at"]).alias("fetched_at"),
        F.col("value").alias("payload"),
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_modification_time").alias("file_modified_at"),
        F.current_timestamp().alias("ingested_at"),
    )


def load_bronze(spark: SparkSession, names: Names) -> int:
    """Append the new files of the raw volume to the bronze table. Returns how many files it read.

    The table is append-only, so the files read are the rows it gained: under Spark Connect the progress of an
    ``availableNow`` query can leave ``numInputRows`` empty.
    """
    before = spark.table(names.bronze).count()
    files = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "text")
        .option("wholetext", "true")  # one row per file: a payload.json is a single JSON document
        .option("pathGlobFilter", "payload.json")
        .option("cloudFiles.allowOverwrites", "true")
        .load(names.raw_volume)
        .select("value", "_metadata")
    )
    query = (
        payload_rows(files)
        .writeStream.option("checkpointLocation", names.checkpoint)
        .trigger(availableNow=True)
        .toTable(names.bronze)
    )
    query.awaitTermination()
    read = spark.table(names.bronze).count() - before
    log.info("bronze: %d new payload files -> %s", read, names.bronze)
    return read
