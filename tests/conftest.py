import logging

import pytest


@pytest.fixture(scope="session")
def spark():
    pyspark_sql = pytest.importorskip("pyspark.sql")
    session = (
        pyspark_sql.SparkSession.builder.master("local[1]")
        .appName("mdp-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()
    # py4j logs "Closing down clientserver connection" at interpreter exit, after pytest
    # has closed its log streams; silence it to keep the test output clean.
    logging.getLogger("py4j").setLevel(logging.WARNING)
