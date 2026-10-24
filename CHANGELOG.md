# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added

- SOCIB connector: real observations from 3 weather stations and the Bahía de Palma buoy via THREDDS NCSS (CSV,
  no API key). Raw 1-10 minute samples land in bronze; `normalize` aggregates them to hourly values using only
  samples the SOCIB QC marks as good. Metric names and units match Open-Meteo for station-vs-model comparison.
- `source_qc` quality rule: rows a connector labels `suspect` from the source's own QC keep that label and are
  counted in `quality.check_results`.
- `RawPayload.partition` (one bronze object per station/partition within a dataset) and `HttpClient.get_text`
  for non-JSON responses.
- Grafana: station (SOCIB ParcBit) vs model (Open-Meteo Palma) chart and latest SOCIB readings table.
- Grafana map with one layer per georeferenced source: Open-Meteo points coloured by EAQI and SOCIB stations
  with their latest temperature, humidity and wind. REData stays off the map (system-wide, not a point).

### Fixed

- Map labels were unreadable (yellow on yellow) and coordinates showed float noise from `avg()`
  (`39.4983999999987`); `dim_locations` now rounds them to 6 decimals.

## [0.2.0] - 2026-10-24

Second connector: electricity of the Balearic system from Red Eléctrica.

### Added

- REData connector (Red Eléctrica, Balearic electric system): hourly electricity demand (28-day request
  chunks, the API rejects hourly ranges of one calendar month or more), daily generation
  mix by technology and daily CO2 emissions and intensity. Series are mapped to metrics in `connector.yaml`;
  unmapped series are logged instead of silently dropped.
- Per-dataset `frequency` in `connector.yaml`: the gaps rule checks each group of metrics against its own
  sampling frequency, so one connector can mix hourly and daily datasets.
- `TimeWindow.split(max_days)` to page APIs that limit the date range per request.
- Grafana: electricity row with hourly demand, daily generation mix and CO2 intensity.
- E2E runs every connector and checks that each one loaded data.

### Fixed

- `No module named core.cli` after switching git branches: per-folder bind mounts kept pointing at folders
  git had deleted and recreated. Compose now mounts the whole checkout read-only and Airflow reads the DAGs
  from `/opt/project/dags`.

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

[Unreleased]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/releases/tag/v0.1.0
