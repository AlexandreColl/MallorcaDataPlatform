"""The data model documents every dbt model, its contracts and its naming exceptions, and stays in step with dbt.

docs/data-model.md holds the method (dimensions, facts and their grain, naming conventions) and dbt/README.md the
catalogue model by model. A model added without its line in both fails here, and so does a mart whose name breaks the
naming convention without being listed among the documented exceptions.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
DBT = ROOT / "dbt"
DATA_MODEL = (ROOT / "docs" / "data-model.md").read_text(encoding="utf-8")
DBT_README = (DBT / "README.md").read_text(encoding="utf-8")
MARTS_YML = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))

MARTS = sorted(p.stem for p in (DBT / "models" / "marts").rglob("*.sql"))
INTERMEDIATE = sorted(p.stem for p in (DBT / "models" / "intermediate").glob("*.sql"))
SEEDS = sorted(p.stem for p in (DBT / "seeds").glob("*.csv"))
SNAPSHOTS = sorted(
    snapshot["name"]
    for path in (DBT / "snapshots").glob("*.yml")
    for snapshot in yaml.safe_load(path.read_text(encoding="utf-8"))["snapshots"]
)


def _mentioned(name: str, text: str) -> bool:
    """Whether ``name`` appears in ``text`` as code (between backticks), not as part of a longer name."""
    return re.search(rf"`[^`]*\b{re.escape(name)}\b[^`]*`", text) is not None


def _section(text: str, heading: str) -> str:
    """The body of a Markdown section, up to the next heading of the same or a higher level."""
    level = heading.split(" ", maxsplit=1)[0]
    (body,) = re.findall(rf"^{re.escape(heading)}\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text, re.MULTILINE | re.DOTALL)
    return body


def test_the_dbt_readme_lists_every_model_seed_and_snapshot():
    missing = [name for name in MARTS + INTERMEDIATE + SEEDS + SNAPSHOTS if not _mentioned(name, DBT_README)]
    assert missing == []


def test_the_data_model_gives_every_fact_its_grain_and_every_dimension_its_key():
    facts = _section(DATA_MODEL, "### Hechos y grano")
    headings = ("### Dimensiones compartidas", "### Dimensiones de un dominio")
    dimensions = "".join(_section(DATA_MODEL, heading) for heading in headings)
    assert [m for m in MARTS if m.startswith(("fct_", "agg_")) and not _mentioned(m, facts)] == []
    assert [d for d in MARTS + SEEDS if d.startswith("dim_") and not _mentioned(d, dimensions)] == []


def test_every_mart_follows_the_naming_convention_or_is_a_documented_exception():
    exceptions = _section(DATA_MODEL, "## 8. Convenciones de nombres")
    off_convention = [m for m in MARTS if not m.startswith(("fct_", "agg_", "dim_"))]
    assert off_convention, "the exceptions table would have nothing to explain"
    assert [m for m in off_convention if not _mentioned(m, exceptions)] == []


def test_the_dbt_readme_lists_exactly_the_contracted_models():
    contracted = {
        m["name"] for m in MARTS_YML["models"] if m.get("config", {}).get("contract", {}).get("enforced") is True
    }
    lines = _section(DBT_README, "## Contratos").splitlines()
    bullets = "\n".join(line for line in lines if line.startswith(("- ", "  ")))
    assert set(re.findall(r"`(\w+)`", bullets)) == contracted


def test_the_dbt_readme_lists_every_unit_test():
    missing = [t["name"] for t in MARTS_YML.get("unit_tests", []) if not _mentioned(t["name"], DBT_README)]
    assert missing == []
