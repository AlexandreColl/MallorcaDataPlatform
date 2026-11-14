"""Observations as CSV or Parquet files, written from the warehouse rows in batches so memory stays flat."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from api.database import Row

COLUMNS = ("source", "entity", "metric", "ts", "value", "unit", "quality", "lat", "lon")
MEDIA_TYPES: dict[str, str] = {"csv": "text/csv; charset=utf-8", "parquet": "application/vnd.apache.parquet"}
BATCH_ROWS = 50_000


def _cell(value: object) -> object:
    """ISO 8601 for instants (UTC, with the offset), empty for nulls."""
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else value


def csv_chunks(rows: Iterable[Row]) -> Iterator[str]:
    """A header and then the rows, in chunks of ``BATCH_ROWS`` lines."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for i, row in enumerate(rows, start=1):
        writer.writerow([_cell(row[c]) for c in COLUMNS])
        if i % BATCH_ROWS == 0:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
    yield buffer.getvalue()


def parquet_bytes(rows: Iterable[Row]) -> bytes:
    """A Parquet file (zstd) with one row group per batch and ``ts`` as a UTC timestamp."""
    import pyarrow as pa  # noqa: PLC0415 - only exports need it
    import pyarrow.parquet as pq  # noqa: PLC0415

    schema = pa.schema(
        [
            ("source", pa.string()),
            ("entity", pa.string()),
            ("metric", pa.string()),
            ("ts", pa.timestamp("us", tz="UTC")),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("quality", pa.string()),
            ("lat", pa.float64()),
            ("lon", pa.float64()),
        ]
    )
    sink = io.BytesIO()
    with pq.ParquetWriter(sink, schema, compression="zstd") as writer:
        batch: list[Row] = []
        for row in rows:
            batch.append(row)
            if len(batch) == BATCH_ROWS:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []
        writer.write_table(pa.Table.from_pylist(batch, schema=schema))  # also the empty file's only row group
    return sink.getvalue()
