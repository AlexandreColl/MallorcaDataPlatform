"""Command line entry point, usable without Airflow.

Examples:
    python -m core.cli list
    python -m core.cli init
    python -m core.cli run --connectors open_meteo --days 1 --region mallorca
    python -m core.cli backfill --connectors aemet --start 2016-09-01 --end 2026-08-31
    python -m core.cli detect --days 30
    python -m core.cli evaluate
    python -m core.cli correct --days 14
    python -m core.cli evaluate-corrections
    python -m core.cli silver-history
    python -m core.cli silver-changes --version 12 --sources aemet
    python -m core.cli silver-maintain
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date
from typing import TYPE_CHECKING

from core.config import Settings, available_regions
from core.connectors import registry

if TYPE_CHECKING:
    from core.lake import SilverTable

log = logging.getLogger("core.cli")


def _cmd_list(_: argparse.Namespace) -> int:
    for name, cfg in registry.discover().items():
        status = "enabled" if cfg.enabled else "disabled"
        secrets = f" secrets={list(cfg.secrets)}" if cfg.secrets else ""
        print(f"{name:<15} {status:<9} max_days={cfg.max_days:<3}{secrets}  {cfg.description}")
    print(f"\nregions: {', '.join(available_regions())}")
    return 0


def _cmd_init(_: argparse.Namespace) -> int:
    from core.storage import BronzeStore, ensure_bucket
    from core.warehouse import Warehouse

    settings = Settings.from_env()
    store = BronzeStore(settings)
    store.ensure()
    ensure_bucket(store.client, settings.silver_bucket)
    Warehouse(settings).ensure_schema()
    print("buckets and warehouse schema ready")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from core.pipeline import new_run_id, run_connector

    names = args.connectors or registry.runnable_names()
    run_id = args.run_id or new_run_id()
    failures = 0
    for name in names:
        try:
            summary = run_connector(
                name, days=args.days, region_name=args.region, run_id=run_id, catch_up=not args.no_catch_up
            )
            print(json.dumps(summary.as_dict()))
        except Exception:
            log.exception("connector %s failed", name)
            failures += 1
    return 1 if failures else 0


def _cmd_backfill(args: argparse.Namespace) -> int:
    from core.models import TimeWindow
    from core.pipeline import new_run_id, run_connector

    window = TimeWindow(date.fromisoformat(args.start), date.fromisoformat(args.end))
    run_id = args.run_id or new_run_id()
    failures = 0
    for name in args.connectors:
        chunk_days = min(args.chunk_days, registry.discover()[name].max_days)
        for chunk in window.split(chunk_days):  # one run per chunk: a bounded window and memory per run
            # Runs and quality results are keyed by run id and source: each chunk needs its own run id.
            chunk_run_id = f"{run_id}_{chunk.start:%Y%m%d}"
            try:
                summary = run_connector(
                    name, chunk.n_days, region_name=args.region, run_id=chunk_run_id, catch_up=False, window=chunk
                )
                print(json.dumps(summary.as_dict()))
            except Exception:
                log.exception("connector %s failed for %s..%s", name, chunk.start, chunk.end)
                failures += 1
    return 1 if failures else 0


def _cmd_detect(args: argparse.Namespace) -> int:
    from core.anomaly.runner import detect_anomalies
    from core.pipeline import new_run_id

    summary = detect_anomalies(args.days, sources=args.sources, run_id=args.run_id or new_run_id())
    print(json.dumps(summary.as_dict()))
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from core.anomaly.evaluation import run_evaluation
    from core.pipeline import new_run_id

    rows = run_evaluation(run_id=args.run_id or new_run_id(), days=args.days, seed=args.seed)
    print(f"{'detector':<15} {'fault':<7} {'recall':>7} {'events':>7} {'precision':>9} {'false alarms':>12}")
    for r in rows:
        print(
            f"{r['detector']:<15} {r['fault']:<7} {_pct(r['recall']):>7}"
            f" {r['events_detected']:>3}/{r['events']:<3} {_pct(r['precision']):>9} {r['false_alarms'] or '':>12}"
        )
    return 0


def _cmd_correct(args: argparse.Namespace) -> int:
    from core.corrections.runner import correct_values
    from core.pipeline import new_run_id

    summary = correct_values(args.days, sources=args.sources, run_id=args.run_id or new_run_id())
    print(json.dumps(summary.as_dict()))
    return 0


def _cmd_evaluate_corrections(args: argparse.Namespace) -> int:
    from core.corrections.evaluation import run_evaluation

    rows = run_evaluation(days=args.days, seed=args.seed)
    print(
        f"{'source':<16} {'metric':<21} {'gap':>4} {'hidden':>6} {'fixed':>6} {'support':>7} {'MAE':>8} {'no bias':>8}"
    )
    for r in rows:
        print(
            f"{r['source']:<16} {r['metric']:<21} {r['gap_hours']:>3}h {r['hidden']:>6} {r['corrected']:>6}"
            f" {r['by_support']:>7} {_num(r['mae']):>8} {_num(r['mae_without_bias']):>8}"
        )
    return 0


def _open_silver() -> SilverTable:
    from core.lake import open_silver
    from core.spark import build_spark

    settings = Settings.from_env()
    return open_silver(build_spark(settings, app_name="mdp-silver"), settings)


def _cmd_silver_history(args: argparse.Namespace) -> int:
    print(f"{'version':>7}  {'time (UTC)':<19}  {'operation':<12} {'inserted':>8} {'updated':>8} {'files +/-':>9}")
    for c in _open_silver().history(limit=args.limit):
        files = f"{c['files_added']}/{c['files_removed']}"
        print(
            f"{c['version']:>7}  {c['timestamp']:%Y-%m-%d %H:%M:%S}  {c['operation']:<12}"
            f" {c['inserted']:>8} {c['updated']:>8} {files:>9}"
        )
    return 0


def _cmd_silver_changes(args: argparse.Namespace) -> int:
    from pyspark.sql import functions as F

    try:
        changes = _open_silver().changes(args.version)
    except ValueError as exc:
        print(exc)
        return 1
    if args.sources:
        changes = changes.where(F.col("source").isin(args.sources))
    summary = changes.groupBy("source", "metric", "change").count().orderBy("source", "metric", "change").collect()
    print(f"{'source':<18} {'metric':<24} {'change':<8} {'rows':>7}")
    for r in summary:
        print(f"{r['source']:<18} {r['metric']:<24} {r['change']:<8} {r['count']:>7}")
    for r in changes.orderBy("source", "entity", "metric", "ts").limit(args.limit).collect():
        print(
            f"  {r['source']} {r['entity']} {r['metric']} {r['ts']:%Y-%m-%d %H:%M}"
            f" {r['value_before']} ({r['quality_before']}) -> {r['value_now']} ({r['quality_now']})"
        )
    return 0


def _cmd_silver_maintain(args: argparse.Namespace) -> int:
    _open_silver().maintain(retain_hours=args.retain_hours)
    print(f"silver compacted; files unreferenced for {args.retain_hours} h deleted")
    return 0


def _num(value: float | None) -> str:
    return "" if value is None or math.isnan(value) else f"{value:.2f}"


def _pct(value: float | None) -> str:
    return "" if value is None else f"{value:.0%}"


def _add_silver_commands(sub: argparse._SubParsersAction) -> None:
    silver_history = sub.add_parser("silver-history", help="list the latest commits of the silver Delta table")
    silver_history.add_argument("--limit", type=int, default=20)
    silver_history.set_defaults(func=_cmd_silver_history)

    silver_changes = sub.add_parser("silver-changes", help="rows of silver that changed since a past version")
    silver_changes.add_argument("--version", type=int, required=True, help="a version of `silver-history`")
    silver_changes.add_argument("--sources", nargs="*", help="default: every source")
    silver_changes.add_argument("--limit", type=int, default=20, help="changed rows to print")
    silver_changes.set_defaults(func=_cmd_silver_changes)

    silver_maintain = sub.add_parser(
        "silver-maintain", help="compact silver and delete files time travel no longer needs"
    )
    silver_maintain.add_argument("--retain-hours", type=int, default=168, help="time travel reach (Delta minimum: 168)")
    silver_maintain.set_defaults(func=_cmd_silver_maintain)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run a sub-command. Returns the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="mdp", description="Mallorca Data Platform")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list connectors and regions").set_defaults(func=_cmd_list)
    sub.add_parser("init", help="create buckets and warehouse schema").set_defaults(func=_cmd_init)

    run = sub.add_parser("run", help="run the pipeline for one or more connectors")
    run.add_argument("--connectors", nargs="*", help="default: all enabled connectors")
    run.add_argument("--days", type=int, default=1)
    run.add_argument("--region", default="mallorca")
    run.add_argument("--run-id")
    run.add_argument("--no-catch-up", action="store_true", help="do not recover days missed by failed runs")
    run.set_defaults(func=_cmd_run)

    backfill = sub.add_parser("backfill", help="load a past date range, one run per chunk")
    backfill.add_argument("--connectors", nargs="+", required=True)
    backfill.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    backfill.add_argument("--end", required=True, help="last day, YYYY-MM-DD")
    backfill.add_argument("--chunk-days", type=int, default=365, help="days per run (at most the connector's max_days)")
    backfill.add_argument("--region", default="mallorca")
    backfill.add_argument("--run-id")
    backfill.set_defaults(func=_cmd_backfill)

    detect = sub.add_parser("detect", help="flag anomalies in the recent silver values")
    detect.add_argument("--days", type=int, default=1, help="at least `rescore_days` of config/anomaly.yaml")
    detect.add_argument("--sources", nargs="*", help="default: every connector")
    detect.add_argument("--run-id")
    detect.set_defaults(func=_cmd_detect)

    evaluate = sub.add_parser("evaluate", help="measure the detectors against injected faults")
    evaluate.add_argument("--days", type=int, help="default: `evaluation.days` of config/anomaly.yaml")
    evaluate.add_argument("--seed", type=int, help="default: `evaluation.seed` of config/anomaly.yaml")
    evaluate.add_argument("--run-id")
    evaluate.set_defaults(func=_cmd_evaluate)

    correct = sub.add_parser("correct", help="correct gaps and suspect values of the station series")
    correct.add_argument("--days", type=int, default=1, help="at least `window_days` of config/corrections.yaml")
    correct.add_argument("--sources", nargs="*", help="default: every target of config/corrections.yaml")
    correct.add_argument("--run-id")
    correct.set_defaults(func=_cmd_correct)

    evaluate_corrections = sub.add_parser("evaluate-corrections", help="measure the corrections on hidden values")
    evaluate_corrections.add_argument("--days", type=int, help="default: `evaluation.days` of config/corrections.yaml")
    evaluate_corrections.add_argument("--seed", type=int, help="default: `evaluation.seed` of config/corrections.yaml")
    evaluate_corrections.set_defaults(func=_cmd_evaluate_corrections)

    _add_silver_commands(sub)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
