"""The CI installs dbt from requirements/dbt.txt and the image from its own build arguments: same versions."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        requirement = line.split("#", 1)[0].strip()
        if "==" in requirement:
            name, version = requirement.split("==", 1)
            pins[name.strip().lower()] = version.strip()
    return pins


def _dockerfile_arg(name: str) -> str:
    text = (ROOT / "docker" / "airflow" / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(rf"^ARG {name}=(\S+)$", text, re.MULTILINE)
    assert match, f"{name} not found in the Dockerfile"
    return match.group(1)


def test_ci_dbt_matches_the_image():
    pins = _requirements(ROOT / "requirements" / "dbt.txt")
    assert pins["dbt-core"] == _dockerfile_arg("DBT_CORE_VERSION")
    assert pins["dbt-postgres"] == _dockerfile_arg("DBT_POSTGRES_VERSION")


def test_ci_tflint_matches_the_makefile():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    image = re.search(r"ghcr\.io/terraform-linters/tflint:\S+", makefile)
    assert image
    assert image.group(0) in workflow
