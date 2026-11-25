"""Entry point of every task of the Lakeflow Job: ``main.py <step> --catalog <name> [options]``.

The bundle uploads ``core/``, ``connectors/``, ``config/`` and ``databricks/`` as workspace files with the layout of
the repository, so the repository root is two folders above this file. Both it and ``databricks/src`` go first on
``sys.path``: the job imports the same connector code as Airflow does.
"""

from __future__ import annotations

import argparse
import inspect
import logging
import sys
import uuid
from pathlib import Path


def _repository_root() -> Path:
    """Two folders above this file.

    A ``spark_python_task`` on serverless compute runs the file with ``exec()``, so ``__file__`` is not defined; the
    compiled code still carries the path of the file it came from.
    """
    frame = inspect.currentframe()
    path = frame.f_code.co_filename if frame is not None else sys.argv[0]
    return Path(path).resolve().parents[2]


ROOT = _repository_root()
sys.path[:0] = [str(ROOT), str(ROOT / "databricks" / "src")]

from pyspark.sql import SparkSession

from core.config import load_region
from core.connectors import is_outage, registry
from mdp_databricks.bronze import load_bronze
from mdp_databricks.catalog import Names, setup
from mdp_databricks.gold import build_gold
from mdp_databricks.silver import load_silver
from mdp_databricks.volume_store import VolumeBronzeStore, extract_to_volume

log = logging.getLogger("mdp_databricks")


def _setup(spark: SparkSession, names: Names, args: argparse.Namespace) -> None:
    setup(spark, names, args.readers)
    log.info("setup: catalog %s ready, gold readable by %s", names.catalog, args.readers)


def _extract(_spark: SparkSession, names: Names, args: argparse.Namespace) -> None:
    """One source, the last ``--days`` published days. A source that is down is skipped, not failed (ADR 0022)."""
    connector = registry.load(args.source, secrets={})
    window = connector.config.window(args.days)
    region = load_region(args.region)
    try:
        keys = extract_to_volume(connector, window, region, VolumeBronzeStore(names.raw_volume))
    except Exception as exc:
        if not is_outage(exc):
            raise
        log.warning("extract: %s is unavailable for %s, skipped: %s", args.source, window, exc)
        return
    log.info("extract: %s %s -> %d payloads in %s", args.source, window, len(keys), names.raw_volume)


def _bronze(spark: SparkSession, names: Names, _args: argparse.Namespace) -> None:
    load_bronze(spark, names)


def _silver(spark: SparkSession, names: Names, args: argparse.Namespace) -> None:
    load_silver(spark, names, region=load_region(args.region), run_id=args.run_id or uuid.uuid4().hex)


def _gold(spark: SparkSession, names: Names, _args: argparse.Namespace) -> None:
    build_gold(spark, names)


STEPS = {"setup": _setup, "extract": _extract, "bronze": _bronze, "silver": _silver, "gold": _gold}


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Arguments of one task, as the bundle passes them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=sorted(STEPS))
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--region", default="mallorca")
    parser.add_argument("--readers", default="account users", help="principal granted read access to gold")
    parser.add_argument("--source", help="connector to extract (extract step)")
    parser.add_argument("--days", type=int, default=3, help="days to extract, ending at the last published day")
    parser.add_argument("--run-id", default="", help="lineage id of the silver rows (the job run id)")
    args = parser.parse_args(argv)
    if args.step == "extract" and not args.source:
        parser.error("extract needs --source")
    return args


def main(argv: list[str] | None = None) -> None:
    """Run one step of the pipeline on the session of the serverless task."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    args = parse_args(sys.argv[1:] if argv is None else argv)
    spark = SparkSession.builder.getOrCreate()
    STEPS[args.step](spark, Names(args.catalog), args)


if __name__ == "__main__":
    main()
