# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.2.3] - 2026-10-24

Fifth connector (EMT Palma buses), a pipeline that survives a source outage and recovers the missed days, and
one Grafana dashboard for every source.

### Added

- EMT Palma connector: the static GTFS of Palma's city buses turned into a daily series per stop (scheduled
  departures and lines served), resolving each day's services from the calendar and its holiday exceptions and
  expanding headway-based trips (`frequencies.txt`). The zip lands untouched in bronze with its SHA-256.
- `HttpClient.get_bytes` for binary downloads.
- `dim_sources` dbt seed (label and kind per source) and a test that every source in silver has a row.
- Catch-up: each run extends its window back to the day after the connector's last successful run (up to
  `catch_up_days`, 28 for SOCIB), so the days lost while a source was down are recovered by its next run. DAG
  param `catch_up` and CLI flag `--no-catch-up` to turn it off.
- Failed runs record the exception type in `ops.ingestion_runs.error` (`ConnectTimeout: ...`), so an upstream
  outage can be told from a bug.

### Changed

- Grafana: one dashboard instead of a panel per source, filtered by a multi-select **source** selector (plus
  metric and entity): stats on top, then the map, four charts (metric by source and by entity, Balearic
  electricity, daily quality per source) and a table with every time series. Run and quality-rule tables move to
  a collapsed row. Clearer map symbols: air-quality dots in EAQI colours, thermometers for SOCIB stations, ripples
  sized and coloured by magnitude for earthquakes and a heatmap of EMT bus service.
- A failing source no longer stops the pipeline: `dbt_build` runs with `trigger_rule=all_done` and rebuilds gold
  with whatever loaded. Ingest tasks retry 3 times with exponential backoff (2, 4, 8 min; `MDP_TASK_RETRIES`).
- HTTP client: 10 s connect timeout (fail fast on an unreachable host) and 60 s read timeout, longer backoff.
- E2E: a connector that fails because its API is down (connection errors, timeouts, 5xx) is reported as a GitHub
  warning instead of failing the job; any other error still fails it. Idempotency is checked per source.

## [0.2.2] - 2026-10-24

Fourth connector and the first event source: earthquakes located by the IGN.

### Added

- IGN connector: earthquakes located by the Instituto Geográfico Nacional around Mallorca (region bbox + 1°),
  read from the EMSC FDSN event service (standard API, no key). The IGN's own catalogue is a web form and its
  GeoJSON feed only covers 30 days. Events located by other agencies stay in bronze only.
- Event sources: datasets with `frequency: event` get no gaps rule, and a window without events is a valid run
  with 0 rows (the empty response still lands in bronze). Time-series sources still fail when they return nothing.
- `gold.fct_earthquakes`: one row per earthquake with magnitude, depth and distance to Palma, using the latest
  ingested solution when an agency revises an event.
- Grafana: earthquakes as a layer of the map (star size by magnitude) and a table of every loaded earthquake.
- E2E runs the IGN connector and checks that event sources finish successfully even with no rows.

### Changed

- Event sources are left out of `dim_locations` and `agg_daily_metrics`, which describe time series.
- The "Fuentes activas" stat counts sources with a successful run instead of sources with locations.

## [0.2.1] - 2026-10-24

Third connector: real observations from SOCIB, and a map with every georeferenced source.

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

[Unreleased]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/releases/tag/v0.1.0
