from datetime import UTC, date, datetime

import pytest

from core.models import RawPayload, TimeWindow

pytestmark = pytest.mark.spark


def test_payload_rows_read_the_metadata_and_keep_the_whole_file(spark):
    from pyspark.sql import Row  # noqa: PLC0415 - pyspark is optional outside the spark tests

    from mdp_databricks.bronze import payload_rows  # noqa: PLC0415

    payload = RawPayload(
        source="eea_air_quality",
        dataset="hourly",
        window=TimeWindow(date(2026, 11, 20), date(2026, 11, 22)),
        request={"pollutant": "8"},
        body={"rows": [1, 2, 3]},
        fetched_at=datetime(2026, 11, 23, 6, 30, tzinfo=UTC),
        partition="07040002",
    )
    modified = datetime(2026, 11, 23, 6, 31, tzinfo=UTC)
    path = "/Volumes/mallorca/bronze/raw/" + payload.key
    files = spark.createDataFrame(
        [Row(value=payload.to_json(), _metadata=Row(file_path=path, file_modification_time=modified))]
    )

    row = payload_rows(files).first()

    assert (row.source, row.dataset, row.payload_partition) == ("eea_air_quality", "hourly", "07040002")
    assert (row.window_start, row.window_end) == (date(2026, 11, 20), date(2026, 11, 22))
    assert row.fetched_at.replace(tzinfo=UTC) == payload.fetched_at  # the test session time zone is UTC
    assert RawPayload.from_json(row.payload) == payload
    assert row.file_path == path
