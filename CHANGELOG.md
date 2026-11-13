# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Fixed

- A run left `running` because its process stopped (the computer turned off, the worker killed) and that Airflow
  did not retry is no longer shown as running forever: the next run of the source closes it as `failed`, with the
  error "Interrupted", once it is 12 h old. The Spark cache of a run is released also when its write fails.

### Changed

- The statuses of a run (`running`, `success`, `failed`, `unavailable`) are one list in `core.warehouse.RunStatus`,
  and `tests/test_run_statuses.py` checks that the table CHECK, the dbt test, the API model, `source_health`, the
  Grafana colours, the SLA alert and the web list the same ones. The API documents `last_status` as an enum.
  ADR 0010 records how ADR 0022 changed its handling of outages.
- mypy checks the annotations of `core/` and `api/` in the CI and with `make typecheck`. It found places where a
  Spark query that always returns one row, or a missing JVM gateway, would have failed with an unclear error; they
  now raise a clear one.

## [0.16.2] - 2026-11-11

### Changed

- A source that is down is no longer counted as a failure of the platform (ADR 0022). When a source cannot be
  reached, answers 5xx after the retries, or has not published the window yet, `ops.ingestion_runs` records the run
  as `unavailable` instead of `failed`, and the task is skipped instead of failed, so the DAG run stays green. Its
  retries stay, for short outages. The "Ingesta fallida" alert only fires for `failed`; a long outage is caught by
  the SLA alert, where every run that did not load counts. `gold.source_health` adds `failed_7d` and
  `unavailable_7d`, the API exposes them, and the web shows a "Fuente caída" state and counts outages apart from
  failures. Found with Dataestur, whose API has answered HTTP 500 on every table since at least 10 November.
- GitHub Actions: `actions/setup-node` 7 and `actions/cache` 6.

## [0.16.1] - 2026-11-10

### Changed

- Airflow 3.3.2 → 3.4.0. Inside the image its constraints also bring boto3 1.43.117, pandas 3.1.0, pydantic 2.14.2
  and the OpenLineage provider 2.21.0. The metadata database is reached with psycopg 3 (`postgresql+psycopg://`),
  the driver Airflow 3.4 defaults to. `airflow db migrate` upgrades an existing volume in place; going back to
  3.3.2 needs `airflow db downgrade` first.

- Dependencies: FastAPI 0.162.3, pydantic 2.14.3, psycopg 3.3.8, boto3 1.43.127, pandas 3.1.1, pyarrow 26.0.1,
  ruff 0.17.4, sqlfluff 4.5.0, Vite 8.3.7, @vitejs/plugin-react 6.3.0 and MapLibre 6.17.0.
- pypdf 7.0.1 (major). The water reserves connector only uses `PdfReader` and `extract_text`: the raw text of the
  recorded PDFs changes slightly, but the 355 observations read from each are identical to pypdf 6.
- PySpark stays at 4.2: Delta has no build for Spark 4.3 yet, and Dependabot no longer proposes Spark minors.

## [0.16.0] - 2026-11-10

### Added

- The model is compared with each station at the height of the station. AEMET publishes the height of every
  station and Open-Meteo that of the terrain its model sees at each point; both are now stored in
  `silver.entities.elevation_m` and reach `dim_locations`. `fct_model_bias_daily` and `agg_model_bias_by_station`
  keep the raw bias and add `_adjusted` ones, with the model brought to the station's height at 6.5 °C per km
  (`lapse_rate_c_per_km`). The mountain stations no longer measure the altitude: across the 29 AEMET stations
  with both heights the model's mean absolute error drops from 1.40 to 0.99 °C, and at the Serra d'Alfàbia, 996 m
  above its model cell, the bias goes from +6.0 to −0.4 °C. The API, the web panel and the Grafana panel show both.
- A gap longer than the catch-up is recovered on its own. The catch-up grows a run's window back to
  `catch_up_days`, by default the connector's `max_days` (what its API serves at once). When a source was down
  longer, or the computer off, the run first loads the older days, oldest first, in extra runs of `catch_up_days`
  each (`<run_id>_<first day>`, like a backfill), up to `recover_days` before the end of its window. A failed
  chunk stops the recovery, and the next run resumes after the last chunk that loaded. `recover_days` defaults to
  `catch_up_days` (no change) and is raised only where the API keeps the history: AEMET (1095) and REData (366).
  `RunSummary.recovered_days` counts the recovered days.

### Changed

- Dependencies: FastAPI 0.143.2 → 0.162.0 (API image and CI), boto3 1.43.120 → 1.43.123 and pytest 9.1.1 → 9.2.0.
  The FastAPI `TestClient` runs on `httpx2` instead of `httpx`, which Starlette 1.10 deprecates, so the API tests
  run without warnings.

## [0.15.0] - 2026-11-10

### Added

- Restarts no longer download the same data again (ADR 0021). With `only_missing`, the default of the DAG and of
  `make run`, each connector asks `ops.ingestion_runs` which days of its window no successful load covered: it
  starts at the first missing one, or skips the source entirely (no request, no Spark) when nothing is missing.
  Sources that re-read on purpose to pick up revisions keep their window, once a day. `ONLY_MISSING=false`
  downloads the whole window again (the E2E does, to keep proving idempotency).
- The DAG runs every day by itself (`MDP_SCHEDULE`, default `@daily`, without catch-up): after the computer was off,
  Airflow starts the pending run once as soon as it is back. `MDP_SCHEDULE=none` turns it off (the E2E).

- The pipeline can write the lake with an assumed role (`S3_CREDENTIALS=role`, `core/credentials.py`). Bronze
  (boto3) and Spark (S3A) assume `S3_ROLE_ARN` through STS with temporary credentials that are renewed before they
  expire; `default` uses the SDK's default chain with no keys, and `static` (the default) keeps MinIO's keys.
  `terraform output pipeline_env` gives the role. `make minio-pipeline-user` creates in MinIO the local twin of the
  pipeline role, with the same policy (a test compares it with `iam.tf`), so the role flow runs locally against
  MinIO's STS: a real run writes bronze and merges silver, and is denied deletes in bronze and bucket creation.

### Changed

- `dbt source freshness` follows the SLA of the catalogue: each source's `error_after` is its agreed maximum age
  (`dim_sources.sla_data_age_hours`), next to the earlier `warn_after`. `tests/test_freshness_sla.py` fails if a
  source of the catalogue is not declared to dbt, if `error_after` differs from its SLA, if `warn_after` exceeds it,
  or if a source without an age SLA has a check. AEMET's warnings, Ibestat and the register now have their thresholds
  documented in the data model.

### Fixed

- The pipeline no longer enables versioning on an existing bucket. The pipeline role has no
  `s3:PutBucketVersioning`, and on AWS Terraform creates and configures the buckets.

## [0.14.0] - 2026-11-09

### Added

- Data governance (docs/data-governance.md, ADR 0020). The catalogue of sources (`dim_sources`) gives every source
  its domain, owner, licence with a link to its terms, access (open or a free API key), personal data,
  classification, lifecycle (active or a closed history) and an agreed SLA: the maximum age of its newest value and
  the minimum share of successful runs in 7 days. dbt tests make every field required. Where a publisher states no
  licence (EMT Palma, Dataestur, Ibestat, REData, SOCIB), the entry says so instead of inventing one.
- `gold.source_health` evaluates the SLA (`sla_age_met`, `sla_success_met`, `sla_met`), and `/v1/sources` serves it
  with the governance as nested `governance` and `sla` objects.
- Web, Operación: a *Fuera de SLA* state with the part that is missed, and a *Gobierno del dato* panel (owner,
  licence, access, personal data, SLA). Grafana: an SLA column in *Salud de las fuentes* and a *Fuente fuera de su
  SLA* alert.
- An English README (`README.en.md`), linked from the header of both versions. The detailed documentation stays
  in Spanish.

### Changed

- A closed history is told by its lifecycle in the catalogue, no longer by the age of its newest value (800 days).
- The CI survives a GitHub download outage. A 504 from GitHub's release assets failed the Terraform and dbt jobs
  three times: tflint now runs in its image from ghcr.io (as `make tf-check` does) with its plugins and the
  Terraform providers cached, dbt is installed from `requirements/dbt.txt` with the pip cache (which keeps the
  wheel of dbt-core's parser, built from a GitHub release), and every download is retried by `scripts/ci/retry.sh`
  (pip, `terraform init`, `tflint --init`, the image pull) or by curl itself (the Delta Lake jars). A test keeps the
  dbt pins of the CI equal to the image's and the tflint image equal to the Makefile's.

## [0.13.0] - 2026-11-08

### Added

- Grafana shows the names of the stations, stops and points instead of their identifiers: maps, tables, series
  legends, the anomaly annotations and the selectors (Entidad, Serie corregida), through `gold.dim_locations`.
- Names of the Open-Meteo points: the region's locations and the marine points have a `label` in their YAML
  (`pollenca` is `Pollença`) and the connector describes them.
- API: `name` in `/v1/sea/hourly`.
- Lines of the EMT Palma and CTM networks with their path (`silver.routes`, `dim_routes`):
  - **Path**: GTFS connectors may return the `routes` of a payload, with the shape most trips follow in each
    direction (`shapes.txt`), simplified to about 10 m.
  - **Departures**: a new `scheduled_trips` series per line and day (entity `route_<route_id>`).
  - **Names**: the lines are named like the stops (`1 · Portopí - Sindicat`).
- API: `/v1/mobility/routes`, every line with its path (GeoJSON) and its departures on the latest day.
- API: `/v1/series` lists the daily series of a source (entity, name, metric, unit, days covered) and
  `/v1/series/daily` returns one series day by day: minimum, mean and maximum, completeness, suspect values and the
  instants the anomaly detectors flagged.
- Web: a series explorer (*Explorador*) for any series of the platform:
  - **Selection**: source, metric and entity, over 30 days, a year, five years or the whole history. It stays in the
    address, so a view can be shared.
  - **Figures**: days, completeness, suspect values, anomalies, minimum, mean and maximum.
  - **Charts**: the daily mean over its minimum-maximum band with the flagged days, and the daily completeness.
- Web, Movilidad: map of the bus, train and metro lines in their operator's colour, wider the more departures, filtered
  by network, plus the ten lines with the most departures.

### Fixed

- The transit marts count only the stops (`fct_bus_network_daily`, `fct_island_transit_daily`), not the new line series.
- Web: the home page said fourteen sources; there are fifteen since the Ibestat IPH.
- CI: the API and web exposures list `agg_daily_metrics`, so the API integration tests build it on the empty warehouse.
- Web: the legend of *Temperatura de los últimos 30 días* no longer covers the top of the chart, and the wave chart
  shows one label per day.

## [0.12.0] - 2026-11-07

### Added

- Names of the stops and stations in silver (`silver.entities`). Connectors may describe the entities of a payload:
  the GTFS `stop_name` (EMT Palma, CTM), the AEMET inventory (`PALMA, PUERTO` as `Palma, Puerto`) and the station
  lists of `connector.yaml` (EEA and GOIB air quality, SOCIB). Every run upserts them, so a renamed stop is renamed.
  `dim_locations` has a `name` column and the transit marts the `busiest_stop_name`.
- API: `name` in `/v1/locations`, `/v1/mobility/stops`, `/v1/weather/stations`, `/v1/air-quality/latest` and
  `/v1/corrections`, `station_name` in `/v1/weather/model-bias` and `busiest_stop_name` in `/v1/mobility/daily`.
- Web: the stops and stations show their name instead of the identifier (`stop_452`, `B228`) in the maps and tables.
- API: `date` in `/v1/weather/stations` returns the stations of any day; without it, still the latest with data.
- Web, Tiempo y entorno: a day slider on the temperature by zone, over every day AEMET has published in the last 30
  days. The day under the thumb shows at once and is loaded when the thumb rests (one request per drag, also with
  the arrow keys); the map keeps the previous day until the new one arrives.
- Web, Tiempo y entorno: a play button next to the day slider walks through the days, one a second. It fetches
  every day at once when it starts and moves on only once the day on the map has arrived.
- Connector `ibestat_iph`: the Ibestat Human Pressure Indicator, the people actually present in Mallorca each day
  (residents plus visitors) since 1997, from the eDatos API. Windows end 95 days before yesterday (a month comes out
  at the start of the third month after it) and every run re-reads 120 days, because recent days are estimates.
- dbt: `fct_human_pressure_daily`, the people present against the residents of the INE register of that year.
- API: `/v1/population/pressure`, the people present each day (default: the last two years).
- Web, Movilidad: the people present each day, the last three years laid over each other, against the residents.

### Changed

- Web: the maps update in place. New data of the same layers (another day, another colouring) goes into the
  existing map instead of building a new one, so it no longer flashes grey or loses its zoom.
- Web: the temperature surface draws about seven times faster (about 200 ms a day instead of 1.4 s): the
  interpolation, the blur and the isotherms no longer allocate per pixel, and the isotherms are traced in one pass.

### Removed

- Web, Turismo y recursos: the "Cómo leer la correlación" panel. It explained what a correlation is to readers who
  already know; the electricity chart takes the full width instead.

## [0.11.0] - 2026-11-06

### Changed

- Web, Movilidad: the stop map and the municipality map are now one map, the stops of each network over the
  municipalities, with a selector to colour them (density, service per inhabitant, growth or none) and the figures of
  the municipality or the stop on a click. Service per inhabitant is violet so the blue CTM stops stand out.
- Web, Movilidad: the population of Mallorca since 1996 has a dashed trend line with the mean annual growth.
- Web, Tiempo y entorno: the temperature by zone is smooth. It was square cells of about 1 km; it is now an image
  interpolated pixel by pixel (about 160 m), clipped to the municipal boundaries instead of a rough coastline.
- Web, Tiempo y entorno: the temperature by zone is corrected for altitude. Every station is brought down to the sea
  with the lapse rate (6.5 °C per km), interpolated there and every pixel taken back up to the height of its ground,
  read from the open Terrarium relief tiles (Mapzen terrain on AWS). The Tramuntana is now cold along its ridges
  instead of in rings around its two mountain stations. Isotherms every degree, and the temperature and height under
  the cursor. Without the relief tiles the map falls back to the plain interpolation and says so.
- Web, Movilidad: the map, the table of municipalities and the population chart follow one selected municipality.
  A click on a municipality (map or table) or a choice in the chart highlights it and zooms the map to it.
- Web, Movilidad: the population trend is fitted in one or two stretches (the split that halves the error, if any):
  +2.7 % a year in 1996-2010 and +0.7 % since. The last stretch is carried on to 2030 with its 95 % prediction
  interval.

## [0.10.1] - 2026-11-06

### Fixed

- Chart tooltips froze after passing over a month without data (the tourists of spring 2020, for instance). ECharts 6
  gives the tooltip formatter `undefined` for an empty month and the formatter threw; it now shows a dash.

## [0.10.0] - 2026-11-05

### Added

- Connector `ine_population`: the population of the 53 municipalities of Mallorca on 1 January by sex, from the
  INE municipal register (table 2860, 1996-2025; there was no register in 1997).
  - The core gains `frequency: 1y`: the gaps rule counts calendar years, like months.
  - It comes with the `dim_municipalities` seed (IGN boundaries, simplified), the `fct_population_yearly` mart
    (density and change against the previous register) and the `/v1/population` and `/v1/municipalities`
    endpoints.
  - The mobility dashboard shows the island's population, a map of the municipalities by density, service per
    inhabitant or growth in ten years, the most populated ones and the population since 1996.
- Connector `aemet_warnings`: AEMET weather warnings (Meteoalerta, CAP) of the nine zones of Mallorca, hour by hour
  and per phenomenon (level 0 to 3), from the CAP archive and the latest issue of area 64.
  - Every issue is a snapshot of the warnings in force, and withdrawn warnings disappear without a Cancel, so each
    hour takes the snapshot that was in force.
  - The archive is read in requests of at most 2 days, which is the limit AEMET enforces.
  - It comes with the `dim_warning_zones` seed (zone polygons), the `fct_weather_warnings` mart (warning periods) and
    the `/v1/warnings` and `/v1/warnings/zones` endpoints.
  - The weather dashboard has a map of the zones coloured by level, now or over the next 72 hours, and the list of
    warnings.
- Web front end (`web/`, service `web` on port 3002) with six dashboards in a side menu, each grouping related
  data like the Grafana folders:
  - home: five key figures against the usual value of their month, and a map of stations and model points;
  - tourism and resources, each pair of series with its 12-month trend and Pearson correlation, raw and without
    the yearly cycle (tourists vs water reserves: r −0.53, −0.41 without it);
  - climate and water;
  - mobility, with a map of the service of each stop;
  - weather and environment: temperature by zone (the AEMET stations interpolated over the island), air quality
    now on a large map with its stations, waves, episodes, earthquakes and model error;
  - operations: source health, failing quality rules, anomalies per day and the latest corrections.

  Built with React, TypeScript and Vite, with ECharts and MapLibre on OpenStreetMap tiles. Light and dark mode
  with a button (remembered in the browser), a logo with the island's silhouette in pine green, and a drawer menu
  on phones. It reads only the REST API: nginx serves the build and proxies `/api`. CI typechecks, tests and
  builds it, and builds its image; releases publish it to GHCR. ADR 0019 records why a web of its own and not a
  redesign of Grafana.
- REST API endpoints for the dashboards:
  - `/v1/locations`;
  - `/v1/mobility/daily` and `/v1/mobility/stops`;
  - `/v1/weather/daily`, `/v1/weather/stations`, `/v1/weather/episodes` and `/v1/weather/model-bias`;
  - `/v1/air-quality/latest`, `/v1/sea/hourly` and `/v1/earthquakes`;
  - `/v1/quality/rules` and `/v1/anomalies/daily`.

  Each has unit tests and runs against the warehouse in CI.
- dbt exposure `web`: the marts the web front end reads through the API. The `rest_api` exposure lists the new
  marts too, so CI builds them before testing the API.

### Changed

- Architecture diagram in light and dark (it follows the reader's theme), generated by
  `scripts/architecture/diagram.mjs` with Simple Icons logos. It replaces the Mermaid flow at the top of the README.
- The README opens with the web front end, in light and dark mode, and shows every web dashboard. The Grafana
  screenshots move to `docs/img/grafana/`, and `make screenshots` takes both sets (`scripts/web_screenshots.py`).
- Movilidad shows one key figure per network: its stops with service go next to its scheduled departures.

### Fixed

- `dim_date` starts in 1996, the first municipal register; it started in 2002.
- The web shows the municipal register as current: its newest value can be almost two years old before the next one
  is published, and the one-year limit showed it as a closed history.
- The README, the data model and the web home counted twelve sources; there are fourteen, and the footer credits the
  INE.

## [0.9.0] - 2026-11-04

### Added

- Data model (`docs/data-model.md`): conceptual model, the long silver table with its key and the meaning of each
  column, the gold star with the grain and type of every fact, shared dimensions and their history policy,
  contracts at three boundaries, time, unit and null conventions, freshness per source and schema evolution rules.
- `dim_metrics` in gold: one row per source and metric with its unit and coverage. Its primary key makes one unit
  per metric part of the contract.

- Architecture case study (`docs/architecture.md`): context and constraints, overview and sequence diagrams of a
  run, 13 design decisions with why, the alternatives ruled out and what each costs, quality attributes and known
  limits.
- Trade-offs, costs and scaling in the architecture case: today's measured volumes, what each decision gains and
  costs and when to revisit it, what breaks first at 10× and 100×, and an AWS cost estimate (the lake costs cents,
  always-on compute is the real cost).
- Architecture decision records (`docs/adr/`): 18 ADRs with status and date, a template and an index, including
  the superseded and rejected ones (silver in Parquet, USGS earthquakes, OpenAQ). Each says when to revisit it.
  Section 3 of the architecture case is now a summary that links to them.
- Roadmap phase towards data architecture: ADRs, documented data model, a real AWS deployment and a second engine.
- Lineage with OpenLineage. The DAG tasks declare the datasets they read and write as Airflow assets (bronze, the
  silver Delta table, `silver.observations`, `silver.anomalies` and `silver.corrections`), and the OpenLineage
  provider sends them with each run. `dbt_build` runs `dbt-ol`, which adds one job per model and test, with its
  inputs, output and column lineage, under the task run. Both sides name the tables alike, so the graph goes from
  ingestion to gold. Optional Marquez backend (`COMPOSE_PROFILES=lineage` and `OPENLINEAGE_URL` in `.env`, UI at
  http://localhost:3001); without `OPENLINEAGE_URL` nothing is sent and dbt runs as before.
- Integration tests of the warehouse writes against Postgres (`tests/test_warehouse.py`, a CI step on the dbt job's
  database): a rerun with the same content writes nothing, a changed value or quality updates only its row and its
  `updated_at`, the catch-up day comes from successful runs only, and anomalies are replaced only inside their window.

### Changed

- `dim_locations` has a contract with its primary key, and `dim_date` starts in 2002 so it covers every day with
  data (it started in 2020 and the air quality history goes back to 2002). `agg_daily_metrics.local_date` is tested
  against it.
- Silver is a Delta Lake table (`core/lake.py`). Each connector run MERGEs its rows on the key instead of overwriting
  its Parquet partitions; rows that did not change are dropped first, so a rerun without changes writes no file and
  no version. A Postgres advisory lock serialises the commits of the two Spark drivers the DAG runs at once, since
  Delta on S3 has no atomic put-if-absent from Spark.
- One partition per source instead of per source and day: the old lake had 16,973 partitions of ~17 KB (67,000
  files). The first run converts it in place (`CONVERT TO DELTA`) and rewrites it once by source (29 files); MERGEs
  and queries on a few days skip the other files through the Delta min/max statistics.
- New `make silver-history` (commits with the rows inserted and updated), `make silver-changes VERSION=n` (rows
  added, removed or changed since a version, read from the Change Data Feed) and `make silver-maintain`
  (`OPTIMIZE … ZORDER BY (ts)` into files of up to 32 MB, then a 7-day `VACUUM`). On the real lake, OPTIMIZE takes
  2.7 min and leaves 12 files.
- The Airflow image adds the Delta 4.4.1 jars for Spark 4.2 (no Python package: `delta-spark` pins an older
  PySpark), and CI passes the same jars to the test SparkSession.
- Terraform: the Glue table `observations` is a Delta table (`table_type = DELTA`) that Athena reads through the log,
  so files a MERGE replaced never reach the results. Partition projection and the `sources` and `history_start`
  variables are gone.
- Failures that waiting will not fix skip the task retries (2, 4 and 8 min): a source that has not published the
  window yet (`SourceNotUpdatedError`) or an HTTP 4xx other than 408 and 429. The stale EEA feed now fails in 7 s
  instead of about 14 minutes; outages (connection errors, 5xx) keep their retries.
- Delta auto compaction: after a write, the new file of the source is compacted with its old ones (files of up to
  32 MB), so silver keeps one file per source between `make silver-maintain` runs.
  The table state is rebuilt with 2 tasks instead of 50, which saves about 5 s per connector run. Ingest tasks take
  37-60 s instead of 58-105 s.
- `VACUUM` lists the table's files with 8 tasks instead of up to 10,000: 5 s instead of 55 s on a small table.
- Cleanup: the silver key and compared columns are defined once (`core/models.py`) for the Delta MERGE, the Postgres
  upsert and the duplicate rule; unused code is gone. The README and architecture diagrams are simpler: a linear data
  flow and a services view.

### Fixed

- SOCIB: the THREDDS server moved its subset service from `/ncss/` to `/ncss/point/` (the old path answers 404),
  and its `dataset.xml` sometimes leaves out the time coverage. The connector uses the new path and reads the
  coverage from the file's NcML (`time_coverage_start`).

## [0.8.0] - 2026-11-01

### Added

- Verified EEA air quality data (E1a) for previous years: `eea_air_quality` splits the window by year and reads the
  current year from the up-to-date files and earlier years from the verified ones (2013 onwards). A backfill of July
  2021 to 2025 closes the gap between the GOIB history and the live feed, so `fct_air_quality_monthly` is continuous
  from 2002. Verified files hold every year, so they are downloaded once per process.
- Corrections with support sources (phase 4, `core/corrections`): the hourly stations (SOCIB, EEA) get a proposed
  value for every hour without a valid one (missing, suspect or without a row), stored in `silver.corrections` with
  the original value, the method, the support series, its bias and a confidence; `silver.observations` never
  changes. Gaps of up to 3 hours are interpolated; longer ones take the best correlated series of the same metric
  within 30 km (another station or the Open-Meteo point, r >= 0.6), shifted by its bias calibrated per hour of the
  day on the previous 30 days. New DAG task `correct_values`, `make correct` and `make evaluate-corrections`, which
  hides clean values in gaps of 1-24 h and measures the error of each method (temperature: 0.26 °C in one hour,
  1.35 °C in 24 h with a support against 2.19 without its bias). `gold.fct_observations_corrected` shows both
  values side by side, and the Operación dashboard has corrections per day, a before/after chart of the chosen
  series and the latest corrections.
- `GET /v1/corrections` in the REST API: the proposed values of the station gaps with the original value and
  quality, the method, the support, its bias and the confidence, filtered by source, station, method and time range,
  paginated.
- Anomalies as Grafana annotations on the series: the metric explorer of Tiempo y entorno, the stations' NO2 (off by
  default) and the before/after chart of Operación. Consecutive anomalous hours of a series are one band with the
  range of values and the expected value.

### Changed

- `eea_air_quality` keeps in bronze only each file's rows of the window (unchanged, as Parquet), with the SHA-256 and
  size of the whole file, instead of the whole file: a verified file holds thirteen years. The `dataset` option is
  gone: the extractor picks the dataset by year.

### Fixed

- A source that has stopped publishing for a while is an upstream outage, not a bug: `eea_air_quality` raises the
  new `SourceNotUpdatedError` when the window has no rows and every file ends before it (the EEA published nothing
  from 30 October to 1 November 2026), and the E2E treats it as a warning like a connection error.

## [0.7.0] - 2026-10-31

### Added

- Terraform for AWS in `infra/terraform`, not deployed: S3 buckets for bronze, silver and Athena results (private,
  SSE-S3, TLS only, versioning and lifecycle rules, through a reusable module), least-privilege IAM roles for the
  pipeline and for analysts, a Glue Data Catalog table over the silver Parquet with partition projection, an Athena
  workgroup with a per-query scan limit and a 2 USD monthly budget. CI runs `fmt`, `validate`, tflint with the AWS
  ruleset and 13 `terraform test` runs against a mocked AWS provider, with no account or cost (`make tf-check`).

- Coverage gate and badge: CI fails when `core/` drops below 80 % (branches included; now 84 %, with new tests
  for the CLI and the HTTP client), and `dbt-docs.yml` publishes the HTML report and a shields.io badge endpoint
  on GitHub Pages next to the dbt docs.
- Screenshots of the six Grafana dashboards in the README, regenerated with `make screenshots`
  (`scripts/grafana_screenshots.py`, Playwright in Docker against the local stack).
- Grafana alert rules, provisioned from `dashboards/provisioning/alerting/alerting.yml` and evaluated every 5 minutes on
  `ops.ingestion_runs` and `quality.check_results`: failed ingestion, an active source without a successful run in 36 h
  (history backfills excluded), and a quality rule that passed in the previous check and fails in the last one. The
  Operación dashboard lists the active alerts.
- Optional Telegram notifications for those alerts: with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`,
  the Grafana entrypoint provisions a Telegram contact point and routes every alert to it (grouped per rule and
  source, repeated every 12 h while firing); without them, or when they are removed, there is no contact point.

### Changed

- Grafana Inicio: the map zooms on the island, clear of the layer legends, and is taller.

## [0.6.0] - 2026-10-29

### Added

- EEA air quality connector (`eea_air_quality`): hourly NO2, O3, PM10, PM2.5, SO2 and CO of the 9 official stations of
  Mallorca from the EEA Air Quality Download Service (JSON search, one Parquet per sampling point, no API key).
  OpenAQ was probed first and carries only about 30 % of their hours. dbt `fct_air_quality_model_bias_daily`
  compares each station with the Open-Meteo CAMS model; Grafana shows the stations on the Inicio map and the model
  bias in Tiempo y entorno.
- `HttpClient.post_text` for read-only JSON searches (retried like GETs).
- GOIB air quality history connector (`goib_air_quality`): hourly NO2, O3, PM10, PM2.5, SO2 and CO of 11 official
  stations of Mallorca, 2002 to June 2021, from the Govern open data catalogue (CKAN, no API key). History only:
  disabled in the daily run and loaded with `make backfill`. dbt `fct_air_quality_monthly` joins it with the EEA
  feed per station; Grafana shows 20 years of NO2 and the yearly island means in Tiempo y entorno.

### Changed

- Roadmap: aqicn probed and not integrated. Its 7 Mallorca stations are the Govern ones the EEA connector already
  reads, with only the latest hour and as US AQI sub-indices instead of concentrations.
- Releases also publish the REST API image on GHCR (`api:X.Y.Z` and `api:X.Y`), and the release workflow checks that
  the tag matches the versions of `pyproject.toml`, `core` and `api`. It can be run by hand with an existing tag to
  publish that tag's images without touching its GitHub Release (tags from v0.5.0 on).

### Fixed

- `water_reserves` reads the period of the 10-year PDF when its title wraps before the last year, as in the
  chart published on 2026-10-29 (up to September 2026).

## [0.5.0] - 2026-10-29

A read-only REST API over the gold marts, so the data behind the dashboards can be used by other applications.

### Added

- REST API (`api/`, FastAPI): read-only access to the gold marts in its own small image and compose service (port
  8000, OpenAPI docs at `/docs`). Endpoints for health, sources, paginated observations and anomalies, water
  reserves and aquifers, and the climate, tourism and resources monthly marts. Read-only database role
  `api_reader` (`make api-role` on an existing volume), one error shape, unit tests with a fake database and
  integration tests that run every query against the marts in CI; the E2E checks that the API serves the loaded data.
- dbt exposure `rest_api`: the marts the API reads. CI builds its lineage before the API integration tests, whatever
  slim CI selected.

## [0.4.0] - 2026-10-29

Three new open-data sources (CTM island transport, Dataestur tourism and the Govern's groundwater reserves), ten
years of history through backfills, and Grafana reorganised into six themed dashboards that put tourism, water and
climate side by side.

### Added

- CTM connector (`ctm`): the Consorci de Transports de Mallorca static GTFS (TIB buses, SFM trains, metro) as a
  daily series per stop, 763 stops island-wide. dbt `stg_ctm__observations` and `fct_island_transit_daily`; CTM
  joins EMT in the Grafana heat map.
- Dataestur connector (`dataestur`): monthly Balearic tourism from SEGITTUR (FRONTUR international tourists, EGATUR
  spending, EOH hotel occupancy, AENA Palma airport passengers), read from xlsx with the standard library. dbt
  `fct_tourism_monthly` (spending per tourist, year-on-year change) and a Grafana panel of the last three years.
- Water reserves connector (`water_reserves`): Mallorca's groundwater reserves from the Govern's water portal,
  monthly per aquifer (spreadsheet of the last 13 months) and 10 years island-wide (bar labels of the PDF chart, read
  with `pypdf`). dbt `fct_water_reserves_monthly` (anomaly against the same calendar month) and seed `dim_aquifers`.
- Backfills: `python -m core.cli backfill` and `make backfill CONNECTORS=aemet START=... END=...` load a past date
  range with explicit windows, one run per chunk of at most the connector's `max_days`, without catch-up.
- dbt `fct_climate_monthly`: monthly rainfall and temperature of the AEMET stations (stations with at least 90 % of
  the month), anomalies against the same calendar month, hot days and the rainfall of the hydrological year. With
  ten years of AEMET loaded it is the climate side of the water dashboards.
- Monthly sources in the core: `frequency: 1mo` (the gaps rule counts calendar months) and `min_days`, the shortest
  window a run asks for, so the daily one-day run of a monthly source re-reads its last year.

### Changed

- Grafana: the single overview is split into six themed dashboards linked to each other: **Inicio** (last month of
  water, climate and tourism, and the map), **Turismo y recursos** (tourists against groundwater reserves and
  electricity demand, with anomalies against the same month and a year-by-year evaluation), **Clima y agua**
  (rainfall, temperature and the response of the aquifers), **Movilidad**, **Tiempo y entorno** and **Operación**.
  New dbt mart `fct_resources_monthly` and one dbt exposure per dashboard.
- The GTFS logic moves from the EMT Palma connector to `core/connectors/gtfs.py` (`GtfsConnector`), shared by EMT
  and CTM; `fct_bus_network_daily` is now built by the `transit_network_daily` macro (same columns).
- Dependencies: PySpark 4.2.1 (still Hadoop 3.5.0, so hadoop-aws 3.5.0 and AWS SDK 2.35.4 stay), ruff 0.17.3, and
  in CI pandas 3.1.0, pyarrow 26.0.0 and boto3 1.43.120 (the image keeps the versions of the Airflow 3.3.2
  constraints). The AWS SDK bundle is not bumped to 2.57: it must match the hadoop-aws build.

### Fixed

- Backfills give each chunk its own run id: the runs and quality results of a chunk no longer overwrite the
  previous one.
- The bus heat map computed the last day of each network with a correlated subquery that took minutes on ten years
  of daily aggregates; it is now computed once per network (0.3 s).
- dbt slim CI builds the parents of the modified models' children (`@state:modified`): a changed seed no longer
  fails on tests whose other parents were never built.

## [0.3.0] - 2026-10-27

Anomaly detection: two detectors that flag silver values without changing them, measured against injected faults.
Also two Grafana panels built on the dbt marts, and the new open-data sources probed for the roadmap.

### Added

- Anomaly detection (phase 3, first block): `Detector` interface in `core/anomaly/` (pandas, distributed per series
  with `applyInPandas`) and the robust z-score detector (rolling median and MAD; 7-day window for hourly series,
  31 days for daily ones). Flags go to `silver.anomalies` and never change silver.
- DAG task `detect_anomalies` after ingestion (`all_done`), re-scoring at least the last `rescore_days` and replacing
  its previous result; `config/anomaly.yaml`, `python -m core.cli detect` and `make detect`.
- Fault-injection benchmark: `FaultInjector` (spikes, frozen sensors, drifts on Open-Meteo series, seeded) and the
  precision and recall of every detector, by value and by fault, in `quality.anomaly_evaluations`
  (`python -m core.cli evaluate`, `make evaluate`). Robust z-score: 90 % of spikes, 22 % of drifts, no frozen
  sensors, 80 % precision.
- Isolation Forest detector (scikit-learn), multivariate per location: value, change, run of unchanged values and
  distance to the usual value at that hour for every metric, plus the hour of day; flags 5 % of each location's
  timestamps and blames the metric that strays furthest. Catches 52 % of frozen sensors (z-score 0 %) and 49 % of
  spikes at 85 % precision. Detectors now score a whole entity (`score_entity`; `UnivariateDetector` for
  per-metric ones) and the runner groups by source and entity.
- Clock-shift fault (values from 12 hours earlier) in the benchmark; neither detector catches more than 6 %.
- Grafana: station vs model temperature error and weather episodes panels, from the dbt marts.

### Changed

- pandas, pyarrow and scikit-learn are explicit runtime dependencies (already in the image through the Airflow
  constraints).
- Roadmap: CTM/TIB (GTFS of the whole island) and Dataestur (tourism) probed and planned as connectors; GOIB air
  quality is history only (its CSVs end in 2019).
- PR titles accept the `anomaly` scope.

### Removed

- Grafana: the daily quality per source and Balearic electricity panels (repeated the stats, the series table and
  the metric selector).

## [0.2.5] - 2026-10-27

dbt in depth: staging, intermediate and domain marts, incremental facts, per-source freshness, station vs model
bias, weather episodes, an SCD2 snapshot, packages, contracts, unit tests, exposures, docs on GitHub Pages, slim CI
and sqlfluff.

### Added

- dbt exposures: the Grafana dashboard and the planned corrections phase, in the lineage graph and selectable
  (`+exposure:grafana_overview`).
- `dbt docs` published to GitHub Pages on every push to `develop` (workflow `dbt-docs.yml`), which also keeps the
  `develop` manifest; `scripts/github-setup.sh` enables Pages with the Actions source.
- Slim CI: pull requests build `+state:modified+` against the `develop` manifest (full build when there is none).
- `sqlfluff` 4.4 with the dbt templater in CI, reported as PR annotations; existing models fixed.

- Station vs model: `int_station_model_pairs` (nearest Open-Meteo point within 25 km, `haversine_km` macro),
  `fct_model_bias_daily` and `agg_model_bias_by_station` (bias, MAE, RMSE, rain bias and rainy-day agreement).
- Weather episodes: `int_weather_extremes__daily` and `fct_weather_episodes` (consecutive days of heavy rain,
  strong wind or rough sea grouped with gaps and islands; thresholds in `vars`).
- SCD2 snapshot `snap_locations` of station, model point and stop coordinates.
- dbt packages `dbt_utils` 1.4.1 and `dbt_expectations` 0.10.10 (lockfile), installed in the image; `dim_date`
  on `dbt_utils.date_spine`, `episode_id` with `generate_surrogate_key`, recency and expression tests.
- Model contracts (`contract: enforced`, primary keys) on `dim_date`, `fct_electricity_daily`,
  `fct_bus_network_daily`, `agg_model_bias_by_station` and `fct_weather_episodes`.
- dbt unit tests: European AQI band, Haversine distance and event revisions, episode grouping.


- dbt marts by domain: `fct_weather_daily` (AEMET and SOCIB observations next to the Open-Meteo model on common
  columns), `fct_sea_conditions_hourly`, `fct_electricity_daily` (renewable share and net import through the link
  with the mainland), `fct_bus_network_daily`, `source_health` (last run, failure rate, data age per source) and
  `dim_date`.
- `dbt source freshness` per connector: silver is declared once per connector (same table, `filter`) with its own
  threshold (AEMET: 5 days, IGN: none). The DAG runs it before the build, as warnings only.
- Custom generic dbt tests `unique_combination` (model grain) and `value_between`, plus `relationships` to
  `dim_sources`.
- `make dbt-full-refresh`.

### Changed

- `dbt-core` pinned to 1.12.6 in the image and CI: `dbt-postgres` accepts `dbt-core>=1.8.0rc1`, and that
  pre-release marker let pip install a beta.


- dbt project in three layers: `staging` (one view per connector built by the `staging_observations` macro),
  `intermediate` (`int_weather__daily`) and `marts` grouped by domain. Mart names Grafana reads are unchanged.
- `fct_observations` is incremental (merge on silver's `updated_at`, post-hook removes values that became missing)
  and `agg_daily_metrics` is incremental (delete+insert of the series-days touched since the last build).
- Index on `silver.observations (updated_at)` for the incremental watermark.

### Upgrade

- Run `make dbt-full-refresh` once: the existing gold tables do not have the columns the incremental models use.

## [0.2.4] - 2026-10-25

Two weather sources: sea conditions from Open-Meteo Marine and the official AEMET stations.

### Added

- Open-Meteo Marine connector: hourly wave height, period and direction, swell, sea surface temperature, currents
  and sea level (model data) at 8 sea points around Mallorca. A subclass of the Open-Meteo connector that only
  changes the queried points, since the region's locations are inland.
- Grafana: wave layer on the map (colour and label by wave height); the other marine metrics are in the selector.
- AEMET connector: daily climatological values (temperature, rain, humidity, wind, sunshine, pressure) of the 33
  official stations in Mallorca. Handles AEMET's two-step API, ISO-8859-15 data, decimal commas and its limits
  (6 months and 25 stations per request). Needs `AEMET_API_KEY` in `.env`; the E2E runs it when the repository
  has the `AEMET_API_KEY` secret.
- `lag_days` in `connector.yaml` for sources that publish late (AEMET: 3): the window ends that many days before
  yesterday, so `days: 1` asks for the last published day and catch-up never marks an unpublished day as loaded.
- Grafana: AEMET stations on the map with the last published day.

### Changed

- `OpenMeteoConnector.locations()` hook so subclasses can query their own points.
- The default connector selection (DAG param and CLI) skips connectors whose API key is not set, instead of
  failing the run; asking for one explicitly still fails fast naming the missing variable.

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

[Unreleased]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.16.2...HEAD
[0.16.2]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.16.1...v0.16.2
[0.16.1]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.16.0...v0.16.1
[0.16.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.5...v0.3.0
[0.2.5]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/AlexandreColl/MallorcaDataPlatform/releases/tag/v0.1.0
