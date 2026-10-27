"""Runtime settings (from environment variables) and region definitions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from core.models import Location, Region

PROJECT_ROOT = Path(os.environ.get("MDP_PROJECT_ROOT", Path(__file__).resolve().parent.parent))


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    """Platform settings. Defaults target a local run against the docker compose stack."""

    project_root: Path
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    s3a_input_stream: str
    bronze_bucket: str
    silver_bucket: str
    warehouse_host: str
    warehouse_port: int
    warehouse_db: str
    warehouse_user: str
    warehouse_password: str
    spark_master: str
    spark_driver_memory: str
    spark_extra_jars: str

    @classmethod
    def from_env(cls) -> Settings:
        """Read every setting from environment variables (see ``.env.example``)."""
        return cls(
            project_root=PROJECT_ROOT,
            s3_endpoint_url=_env("S3_ENDPOINT_URL", "http://localhost:9000"),
            s3_access_key=_env("S3_ACCESS_KEY", "minioadmin"),
            s3_secret_key=_env("S3_SECRET_KEY", "minioadmin"),
            s3_region=_env("S3_REGION", "us-east-1"),
            # classic works with any S3-compatible store; `analytics` is tuned for AWS S3.
            s3a_input_stream=_env("S3A_INPUT_STREAM", "classic"),
            bronze_bucket=_env("BRONZE_BUCKET", "bronze"),
            silver_bucket=_env("SILVER_BUCKET", "silver"),
            warehouse_host=_env("WAREHOUSE_HOST", "localhost"),
            warehouse_port=int(_env("WAREHOUSE_PORT", "5432")),
            warehouse_db=_env("WAREHOUSE_DB", "warehouse"),
            warehouse_user=_env("WAREHOUSE_USER", "warehouse"),
            warehouse_password=_env("WAREHOUSE_PASSWORD", "warehouse"),
            spark_master=_env("SPARK_MASTER", "local[2]"),
            spark_driver_memory=_env("SPARK_DRIVER_MEMORY", "1g"),
            spark_extra_jars=_env("SPARK_EXTRA_JARS", ""),
        )

    @property
    def connectors_dir(self) -> Path:
        """Folder scanned for ``*/connector.yaml``."""
        return self.project_root / "connectors"

    @property
    def regions_dir(self) -> Path:
        """Folder with one YAML file per region."""
        return self.project_root / "config" / "regions"

    @property
    def anomaly_config(self) -> Path:
        """Detectors, their parameters and the series they skip."""
        return self.project_root / "config" / "anomaly.yaml"

    @property
    def jdbc_url(self) -> str:
        """JDBC URL of the warehouse, used by Spark."""
        return f"jdbc:postgresql://{self.warehouse_host}:{self.warehouse_port}/{self.warehouse_db}"


def available_regions(regions_dir: Path | None = None) -> list[str]:
    """Names of the regions defined in ``config/regions``."""
    regions_dir = regions_dir or PROJECT_ROOT / "config" / "regions"
    return sorted(p.stem for p in regions_dir.glob("*.yaml"))


def load_region(name: str, regions_dir: Path | None = None) -> Region:
    """Load ``config/regions/<name>.yaml``.

    Raises:
        ValueError: if the region does not exist.
    """
    regions_dir = regions_dir or PROJECT_ROOT / "config" / "regions"
    path = regions_dir / f"{name}.yaml"
    if not path.exists():
        msg = f"unknown region '{name}'. Available: {available_regions(regions_dir)}"
        raise ValueError(msg)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    bbox = data["bbox"]
    return Region(
        name=data["name"],
        min_lat=float(bbox["min_lat"]),
        min_lon=float(bbox["min_lon"]),
        max_lat=float(bbox["max_lat"]),
        max_lon=float(bbox["max_lon"]),
        locations=tuple(
            Location(name=loc["name"], lat=float(loc["lat"]), lon=float(loc["lon"]))
            for loc in data.get("locations", [])
        ),
    )
