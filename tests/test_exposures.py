"""The REST API exposure lists every gold model the API reads.

On a pull request, CI builds only the modified models and the lineage of ``exposure:rest_api`` before it runs every
API query (api/tests/test_integration.py) on an empty warehouse. A model the API reads but the exposure does not list
does not exist there, and the integration test fails far from its cause.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
EXPOSURES = yaml.safe_load((ROOT / "dbt" / "models" / "exposures.yml").read_text(encoding="utf-8"))["exposures"]
REPOSITORY = (ROOT / "api" / "repository.py").read_text(encoding="utf-8")


def _depends_on(name: str) -> set[str]:
    (exposure,) = [e for e in EXPOSURES if e["name"] == name]
    return {re.fullmatch(r"ref\('(\w+)'\)", ref).group(1) for ref in exposure["depends_on"]}


def test_the_rest_api_exposure_lists_every_gold_model_the_api_reads():
    read = set(re.findall(r"\bgold\.(\w+)", REPOSITORY))

    assert read, "the API reads no gold model: the pattern no longer matches api/repository.py"
    assert sorted(read - _depends_on("rest_api")) == []
