"""Command line entry point, usable without Airflow.

Examples:
    python -m core.cli list
    python -m core.cli init
    python -m core.cli run --connectors open_meteo --days 1 --region mallorca
    python -m core.cli backfill --connectors aemet --start 2016-09-01 --end 2026-08-31
    python -m core.cli detect --days 30
    python -m core.cli evaluate
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

from core.config import Settings, available_regions
from core.connectors import registry

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


def _pct(value: float | None) -> str:
    return "" if value is None else f"{value:.0%}"


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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
