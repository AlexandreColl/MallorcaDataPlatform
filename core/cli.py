"""Command line entry point, usable without Airflow.

Examples:
    python -m core.cli list
    python -m core.cli init
    python -m core.cli run --connectors open_meteo --days 1 --region mallorca
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

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

    names = args.connectors or registry.enabled_names()
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
