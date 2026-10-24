# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.1.0] - 2026-10-24

First release: the platform core with one connector working end to end.

### Added

- Platform core: connector contract (`BaseConnector`, `connector.yaml`), auto-discovery registry,
  HTTP client with retries, region definitions (`config/regions/mallorca.yaml`).
- Bronze layer on MinIO (S3) with deterministic keys and bucket versioning: raw responses are never lost.
- Silver layer with PySpark 4.2: common schema, Parquet lake on S3A and idempotent upsert into PostgreSQL.
- Reusable quality rules: not-null, range, duplicates and gaps, with results in `quality.check_results`.
- Run audit table `ops.ingestion_runs`.
- Open-Meteo connector (air quality + weather, 6 Mallorca locations, 10 hourly metrics) with recorded fixtures.
- Airflow 3.3 DAG `mallorca_pipeline` with parameters and one mapped task per connector.
- dbt gold models and data tests; Grafana 13 dashboard (series, map, data quality, runs) provisioned from code.
- Local stack with Docker Compose: Airflow, PySpark, MinIO, PostgreSQL 18, dbt and Grafana; `Makefile` commands.
- CI on GitHub Actions: ruff, unit tests with PySpark, dbt build, image build and DAG integrity;
  E2E that runs the DAG twice against the real API and checks idempotency; tag-based releases with an
  image on GHCR.
- Repository settings as code (`scripts/github-setup.sh`): rulesets protecting `main` and `develop`.
- Code style: Python 3.14, ruff with every rule enabled, Google-style docstrings, gitmoji + Conventional
  Commits enforced on PR titles, pre-commit hooks.

[Unreleased]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/releases/tag/v0.1.0
