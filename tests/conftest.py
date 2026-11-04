import logging
import os

import pytest

# The Delta Lake build of docker/airflow/Dockerfile. The image and CI pass its jars in SPARK_EXTRA_JARS; elsewhere
# Spark downloads it from Maven Central.
DELTA_PACKAGE = "io.delta:delta-spark_4.2_2.13:4.4.1"


@pytest.fixture(scope="session")
def spark():
    pyspark_sql = pytest.importorskip("pyspark.sql")
    from core.lake import DELTA_SPARK_CONFIG  # noqa: PLC0415 - imports pyspark, skipped above when missing

    builder = (
        pyspark_sql.SparkSession.builder.master("local[1]")
        .appName("mdp-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        # Delta rebuilds the table state from its log with 50 tasks by default: one is plenty for a test table.
        .config("spark.databricks.delta.snapshotPartitions", "1")
    )
    jars = os.environ.get("SPARK_EXTRA_JARS", "")
    builder = (
        builder.config("spark.jars", jars) if "delta" in jars else builder.config("spark.jars.packages", DELTA_PACKAGE)
    )
    for key, value in DELTA_SPARK_CONFIG.items():
        builder = builder.config(key, value)
    session = builder.getOrCreate()
    yield session
    session.stop()
    # py4j logs "Closing down clientserver connection" at interpreter exit, after pytest
    # has closed its log streams; silence it to keep the test output clean.
    logging.getLogger("py4j").setLevel(logging.WARNING)
