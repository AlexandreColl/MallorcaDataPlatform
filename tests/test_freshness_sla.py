"""dbt's freshness checks follow the SLA of the catalogue of sources (dbt/seeds/dim_sources.csv).

The catalogue is the one place where an SLA is agreed (docs/data-governance.md). ``dbt source freshness`` declares
its thresholds in YAML, which cannot read the seed, so this test keeps both in step.
"""

import csv
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOURS = {"minute": 1 / 60, "hour": 1, "day": 24}
# Tables of the silver source that are not one connector's slice of silver.observations.
SHARED_TABLES = {"observations", "entities", "routes", "corrections"}


def _catalogue() -> dict[str, int | None]:
    with (ROOT / "dbt" / "seeds" / "dim_sources.csv").open(encoding="utf-8") as f:
        return {
            row["source"]: int(row["sla_data_age_hours"]) if row["sla_data_age_hours"] else None
            for row in csv.DictReader(f)
        }


def _freshness() -> dict[str, dict | None]:
    sources = yaml.safe_load((ROOT / "dbt" / "models" / "staging" / "_sources.yml").read_text(encoding="utf-8"))
    silver = next(s for s in sources["sources"] if s["name"] == "silver")
    return {
        t["name"]: t.get("freshness", silver.get("freshness"))
        for t in silver["tables"]
        if t["name"] not in SHARED_TABLES
    }


def _hours(threshold: dict) -> float:
    return threshold["count"] * HOURS[threshold["period"]]


CATALOGUE = _catalogue()
FRESHNESS = _freshness()


def test_every_source_of_the_catalogue_is_declared_to_dbt():
    assert set(FRESHNESS) == set(CATALOGUE)


@pytest.mark.parametrize("source", sorted(CATALOGUE))
def test_freshness_follows_the_sla(source):
    sla, freshness = CATALOGUE[source], FRESHNESS[source]

    if sla is None:
        assert freshness is None, f"{source} has no age SLA, so no freshness check"
        return
    assert freshness, f"{source} has an SLA of {sla} h and needs a freshness check"
    assert _hours(freshness["error_after"]) == sla, f"error_after of {source} is its SLA ({sla} h)"
    assert _hours(freshness["warn_after"]) <= sla, f"warn_after of {source} warns before the SLA is breached"
    assert freshness["filter"] == f"source = '{source}'"
