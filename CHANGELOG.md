# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Changed

- Dependencies on their latest releases: PostgreSQL 18.6 (new `postgres18-data` volume mounted at
  `/var/lib/postgresql`), Grafana 13.0.2, gitleaks 8.30.1, boto3/psycopg/pytest-cov in `dev.txt`.
- GitHub Actions on their Node.js 24 majors (checkout v7, setup-python v7, setup-java v6,
  upload-artifact v7, docker/* v4-v7, action-gh-release v3, action-semantic-pull-request v6);
  runners pinned to `ubuntu-26.04`.
- Python 3.14 (Airflow image, CI and `requires-python`).
- Ruff with every rule enabled (`ALL`), 120-character lines and unsafe fixes; documented exceptions only.
  Public modules, classes and functions now have Google-style docstrings and full type hints.
- `run_connector`, `registry.load` and `Warehouse.finish_run` take keyword-only options;
  run counts are passed as a `RunStats` object.

### Fixed

- DAG integrity test failed on Airflow 3.3 (`DagBag(include_examples=...)` removed, `get_dag()` needs the
  metadata DB).
- Spark could not write to `s3a://`: add the S3 Analytics Accelerator jar required by hadoop-aws 3.5.0
  and default the S3A input stream to `classic` (configurable with `S3A_INPUT_STREAM`).
- Default Airflow JWT secret is now long enough for HS512 (removes `InsecureKeyLengthWarning`).
- Grafana map showed "API KEY REQUIRED": use OpenStreetMap tiles instead of the default CARTO basemap.
- "Últimas ejecuciones" showed window dates shifted by the browser timezone.

## [0.1.0] - 2026-10-24

### Added

- Platform core: connector contract (`BaseConnector`, `connector.yaml`), auto-discovery registry,
  HTTP client with retries, region definitions (`config/regions/mallorca.yaml`).
- Bronze layer on MinIO with deterministic keys and bucket versioning.
- Silver layer with PySpark: common schema, Parquet lake on S3A and idempotent upsert into PostgreSQL.
- Reusable quality rules: not-null, range, duplicates and gaps, with results in `quality.check_results`.
- Run audit table `ops.ingestion_runs`.
- Open-Meteo connector (air quality + weather, 6 Mallorca locations) with recorded fixtures.
- Airflow 3 DAG `mallorca_pipeline` with parameters and one mapped task per connector.
- dbt gold models and tests; Grafana dashboard provisioned from code.
- CI (lint, unit tests, dbt, image build), E2E with idempotency check, tag-based releases.
