"""The anomaly detectors and the correction methods are named in several places: they all list core's names.

Adding one (as `seasonal_residual`, `vote` and `profile` were) means changing the CHECK of the corrections table and
its migration, the dbt test, the API, the Grafana labels and the web. A place left behind fails here, instead of
the API answering 500 on a value it does not know or Grafana labelling a new method as an old one.
"""

import json
import re
from pathlib import Path
from typing import get_args

import yaml

from api.schemas import CorrectionMethod, Detector
from core.anomaly.runner import DETECTOR_NAMES
from core.corrections.methods import METHODS

ROOT = Path(__file__).parent.parent
DASHBOARDS = sorted((ROOT / "dashboards" / "json").glob("*.json"))
OPERATIONS_PAGE = (ROOT / "web" / "src" / "pages" / "Operations.tsx").read_text(encoding="utf-8")
# The web names them in each language; Spanish is the reference, and tsc makes Catalan and English have the same keys.
DICTIONARY = (ROOT / "web" / "src" / "i18n" / "es.ts").read_text(encoding="utf-8")


def _queries(dashboard: Path) -> list[str]:
    """Every SQL query of a Grafana dashboard, annotations included."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("rawSql"), str):
                found.append(node["rawSql"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(dashboard.read_text(encoding="utf-8")))
    return found


def _case_labels(column: str) -> list[list[str]]:
    """The values each Grafana `CASE <column> WHEN '<value>' THEN ...` names, one list per CASE."""
    cases = [case for d in DASHBOARDS for q in _queries(d) for case in re.findall(rf"CASE {column} (.*?) END", q)]
    return [re.findall(r"WHEN '(\w+)'", case) for case in cases]


def _web_keys(constant: str) -> list[str]:
    """The keys of a `const <constant>: Record<string, ...> = { ... };` of the Operations page."""
    (body,) = re.findall(rf"const {constant}: Record<string, [^=]+= \{{(.*?)\n\}};", OPERATIONS_PAGE, re.DOTALL)
    top_level = re.sub(r"\{[^{}]*\}", "", body)  # drop the values that are objects: their keys are not names
    return re.findall(r"(\w+):", top_level)


def test_the_api_serves_exactly_these_detectors_and_methods():
    assert get_args(Detector) == DETECTOR_NAMES
    assert get_args(CorrectionMethod) == METHODS


def test_the_corrections_table_accepts_exactly_these_methods():
    ddl = (ROOT / "core" / "sql" / "warehouse.sql").read_text(encoding="utf-8")
    checks = re.findall(r"CHECK \(method IN \(([^)]*)\)\)", ddl)
    assert len(checks) == 2  # the CREATE TABLE and the migration of existing warehouses
    for check in checks:
        assert tuple(re.findall(r"'(\w+)'", check)) == METHODS


def test_dbt_accepts_exactly_these_methods():
    staging = yaml.safe_load((ROOT / "dbt" / "models" / "staging" / "_staging.yml").read_text(encoding="utf-8"))
    model = next(m for m in staging["models"] if m["name"] == "stg_silver__corrections")
    column = next(c for c in model["columns"] if c["name"] == "method")
    (values,) = [t["accepted_values"]["arguments"]["values"] for t in column["data_tests"] if "accepted_values" in t]
    assert tuple(values) == METHODS


def test_grafana_labels_every_detector_and_method():
    detector_cases, method_cases = _case_labels("detector"), _case_labels("method")
    assert len(detector_cases) == 3  # the anomaly bands of Operación, the explorer and the NO2 of the stations
    assert method_cases  # the corrections per day and method
    for labelled in detector_cases:
        assert tuple(labelled) == DETECTOR_NAMES
    for labelled in method_cases:
        assert set(labelled) == set(METHODS)


def _dictionary_keys(table: str) -> list[str]:
    """The keys of a `<table>: { ... },` of the operations texts in the web's Spanish dictionary."""
    (operations,) = re.findall(r"\n  operations: \{(.*?)\n  \},", DICTIONARY, re.DOTALL)
    (body,) = re.findall(rf"\n    {table}: \{{(.*?)\n    \}},", operations, re.DOTALL)
    return re.findall(r"(\w+):", body)


def test_the_web_names_every_detector_and_method():
    assert tuple(_web_keys("DETECTORS")) == DETECTOR_NAMES  # their colours, in the Operations page
    assert tuple(_dictionary_keys("detectors")) == DETECTOR_NAMES
    assert set(_dictionary_keys("methods")) == set(METHODS)
