# Roadmap

Cada versión es una release en GitHub (`vX.Y.Z`) con su entrada en el [CHANGELOG](CHANGELOG.md).
Cada conector es una rama `feature/connector-<nombre>`, un PR a `develop`, un commit `✨ feat(connector): ...`
y una sección en el README.

Leyenda: ✅ hecho · 🟡 en curso · ⬜ pendiente · 🔬 requiere investigación

---

## Fase 0 · Preparación del equipo y decisiones

| Estado | Tarea |
|---|---|
| ✅ | Nombre del proyecto: **MallorcaDataPlatform** |
| ✅ | Comprobar Docker → **no está instalado** (WSL presente, sin distribución). Ver [docs/setup-windows.md](docs/setup-windows.md) |
| ✅ | WSL2 con Debian 13 (trixie) |
| ✅ | Docker Engine, git y make dentro de Debian; `.wslconfig` con 10 GB ([guía](docs/setup-windows.md)) |
| ✅ | Clonar el repo en el sistema de ficheros de Debian (`~/projects`) y GitHub CLI (`gh`) |
| ⬜ | Confirmar **Grafana** como visor principal (implementado como propuesta en v0.1) |
| ✅ | Probar REData con llamadas reales → funciona, Baleares = `geo_ids=8743`; demanda horaria, generación y CO₂ diarios |
| ✅ | Probar SOCIB → API abierta, 1.598 fuentes, **estaciones activas en Mallorca** (p. ej. `Mobims_CalaMillor`) |
| ✅ | Probar USGS → **0 eventos** en 12 meses en la zona; sustituir por IGN (ver Fase 4) |
| ✅ | Repo público en GitHub, `main` y `develop` protegidas con rulesets (`scripts/github-setup.sh`) |

## Fase 1 · v0.1.0 — Núcleo + Open-Meteo de punta a punta

| Estado | Tarea |
|---|---|
| ✅ | Estructura del repo: `core/`, `connectors/`, `dags/`, `dbt/`, `dashboards/`, `docker/` |
| ✅ | Contrato de conectores: `BaseConnector.extract()` + `normalize()`, `connector.yaml`, registro automático |
| ✅ | Esquema común silver: fuente, entidad, métrica, timestamp, valor, unidad, calidad, lat, lon |
| ✅ | Bronze en MinIO con claves deterministas + **versionado de bucket** (el crudo nunca se pierde) |
| ✅ | Silver con PySpark: Parquet particionado en `s3a://silver` + upsert idempotente en Postgres |
| ✅ | Reglas de calidad reutilizables: nulos, rangos (desde YAML), duplicados, huecos |
| ✅ | DAG parametrizado `{"connectors": [...], "days": N, "region": "mallorca"}`, una tarea por conector |
| ✅ | dbt gold: `fct_observations`, `agg_daily_metrics`, `air_quality_hourly` (EAQI), `dim_locations`, `data_quality_summary` |
| ✅ | Grafana provisionado: datasource de solo lectura + dashboard "Mallorca · Visión general" |
| ✅ | CI: ruff, pytest + PySpark, dbt build, build de imagen, test E2E con idempotencia |
| ✅ | Release automática por tag + imagen en GHCR |
| ✅ | **Primer `docker compose up` real** y `make e2e` en verde (fixes: jar S3A analytics accelerator, mapa OSM en Grafana) |
| ✅ | Primer push a GitHub, CI en verde, release `v0.1.0` |
| ⬜ | Captura del dashboard en el README |

## Fase 2 · v0.2.x — Más conectores (uno por PR)

| Estado | Versión | Conector | Notas de la prueba real |
|---|---|---|---|
| ✅ | v0.2.0 | **REData** (sistema eléctrico balear) | Demanda **horaria** con `demanda/evolucion?time_trunc=hour` (rango < 1 mes natural: bloques de 28 días); generación por tecnología y CO₂ solo diarios. `demanda-tiempo-real` no existe para Baleares. Núcleo ampliado: frecuencia por dataset y `TimeWindow.split` |
| ✅ | v0.2.1 | **SOCIB** (estaciones meteo y boya) | THREDDS NCSS en CSV, sin clave (la API REST `entries` exige clave). 4 estaciones activas en Mallorca; despliegue vigente resuelto del catálogo; agregación horaria con el QC de SOCIB (`source_qc`). Mismas métricas que Open-Meteo → comparación estación vs modelo |
| ✅ | v0.2.2 | **IGN** sismicidad (sustituye a USGS) | El catálogo del IGN es un formulario web (ignora los filtros sin sesión) y su GeoJSON solo cubre 30 días: se leen las localizaciones del IGN desde el **FDSN de EMSC** (estándar, sin clave). Zona muy tranquila: 57 sismos del IGN en 2020-2026 incluso ampliando la caja 1° alrededor de la isla. Núcleo ampliado: `frequency: event` (sin regla de huecos, ventanas vacías válidas) y `fct_earthquakes` en gold |
| ✅ | v0.2.3 | **EMT Palma** (GTFS estático) | Feed abierto en el GitHub de EMT (el NAP exige registro). En lugar de una dimensión estática, una serie diaria por parada (autobuses programados y líneas) a partir del calendario y de `frequencies.txt`. Junto con: **robustez** (una fuente caída no para el DAG, reintentos con espera creciente, recuperación de días perdidos, E2E que avisa de APIs caídas) y **dashboard único** con selector de fuentes |
| ✅ | v0.2.4 | **Open-Meteo Marine** (oleaje y mar) | Sin clave. Los 8 puntos de la costa devuelven datos completos y hay histórico. Subclase del conector de Open-Meteo con sus propios puntos de mar (las localidades de la región están en el interior) |
| ✅ | v0.2.4 | **AEMET OpenData** | Clave gratuita en `.env`. Las observaciones horarias solo cubren las últimas horas: se usan los valores climatológicos diarios (33 estaciones). API en dos pasos, máximo 6 meses y 25 estaciones por petición, publicación con 2-3 días de retraso. Núcleo ampliado: `lag_days` y selección por defecto que omite conectores sin su clave |
| ⬜ | v0.2.6 | **OpenAQ v3** | Requiere `OPENAQ_API_KEY` en `.env`. Comprobar primero si hay estaciones del Govern balear (Bellver, Foners, Sant Antoni…) |
| ⬜ | v0.2.7 | **aqicn** | Requiere `AQICN_TOKEN`. Alternativa a OpenAQ para estaciones reales |
| ⬜ | — | Plantilla `make new-connector NAME=x` que genere la carpeta, YAML y test vacíos |
| ⬜ | — | Script `make record-fixtures CONNECTOR=x` para regrabar respuestas reales |
| ⬜ | — | SOCIB: histórico por ficheros mensuales (`L1/<año>/..._<año>-<mes>.nc`) para ventanas anteriores al `latest`; añadir mareógrafo (Porto Cristo) y oleaje (boyas) |

Criterio de "hecho" por conector: YAML con métricas, unidades y rangos · fixtures reales · tests · aparece en Grafana · sección en README · ≤ 1 día de trabajo.

## Fase 2b · v0.2.5 — dbt avanzado

| Estado | Tarea |
|---|---|
| ✅ | Capas `staging` (una vista por conector, macro común) → `intermediate` → `marts` por dominio ([dbt/README.md](dbt/README.md)) |
| ✅ | Incrementales: `fct_observations` (merge) y `agg_daily_metrics` (delete+insert) con `updated_at` de silver como marca de agua |
| ✅ | `dbt source freshness` por conector (misma tabla, `filter`), solo avisos, antes del build en el DAG |
| ✅ | Marts nuevos: `fct_weather_daily` (observación junto a modelo), `fct_sea_conditions_hourly`, `fct_electricity_daily`, `fct_bus_network_daily`, `source_health`, `dim_date` |
| ✅ | Tests genéricos propios (`unique_combination`, `value_between`) y `relationships` |
| ✅ | Snapshot SCD2 de estaciones, puntos de modelo y paradas (cambios de ubicación) |
| ✅ | Paquetes `dbt_utils` / `dbt_expectations` instalados en la imagen, contratos (`contract: enforced`) en 5 marts y 3 `unit_tests` de dbt (EAQI, Haversine, episodios) |
| ✅ | Sesgo estación vs modelo por día y por estación; episodios meteorológicos con *gaps and islands* (lluvia AEMET + rachas + oleaje) |
| ✅ | Exposures (Grafana y fase de correcciones), `dbt docs` en GitHub Pages, slim CI (`+state:modified+` contra el manifest de `develop`) y `sqlfluff` con el templater de dbt |

## Fase 3 · v0.3.0 — Detección de anomalías

| Estado | Tarea |
|---|---|
| ✅ | Interfaz `Detector` reutilizable en `core/anomaly/` (entrada: serie silver; salida: score + etiqueta): pandas por serie, repartida con `applyInPandas` |
| ✅ | Detector estadístico: z-score robusto (mediana/MAD) sobre ventana móvil, por serie; 7 días en series horarias y 31 en diarias |
| ⬜ | Detector Isolation Forest (scikit-learn) multivariable por localidad |
| ✅ | Tabla `silver.anomalies` (serie, ts, detector, score, umbral, run_id) — **marca, no corrige** |
| ✅ | Tarea `detect_anomalies` en el DAG tras la carga silver (`all_done`); repuntúa los últimos 14 días y es idempotente |
| ⬜ | **Plan B**: inyector de fallos en Open-Meteo (picos, congelados, deriva, huecos) para medir precisión/recall de cada detector |
| ⬜ | Panel de anomalías en Grafana (anotaciones sobre las series) |

## Fase 4 · v0.4.0 — Correcciones con fuentes de apoyo

| Estado | Tarea |
|---|---|
| ⬜ | Tabla `silver.corrections`: valor original, valor corregido, método, fuente de apoyo, confianza, run_id |
| ⬜ | Nunca sobrescribir bronze ni silver: la vista gold elige `coalesce(corregido, original)` y lo indica |
| ⬜ | Método 1: interpolación temporal para huecos cortos |
| ⬜ | Ajuste por altitud del modelo (las estaciones de montaña salen ~6 °C más frías que el punto del modelo a nivel del mar: gradiente de ~6,5 °C/km) |
| ⬜ | Método 2: sustitución por fuente de apoyo cercana (p. ej. estación SOCIB ↔ celda Open-Meteo) con sesgo calibrado |
| ⬜ | Confianza según distancia, correlación histórica y longitud del hueco |
| ⬜ | Modelo dbt `fct_observations_corrected` + panel "antes / después" |

## Fase 5 · v0.5.0 — Calidad de ingeniería

| Estado | Tarea |
|---|---|
| ⬜ | Linaje con OpenLineage (proveedor de Airflow) 🔬 |
| ⬜ | Alertas de Grafana cuando falla una regla de calidad |
| ⬜ | Cobertura de tests ≥ 80 % en `core/` con badge en el README |

## Fase 6 · v1.0.0 — Puente a la nube (los huecos del CV)

| Estado | Tarea |
|---|---|
| ⬜ | **Terraform** para AWS: S3 (bronze/silver con versionado), IAM con mínimo privilegio, Glue Catalog, RDS o Athena |
| ⬜ | Mismo código, otro perfil: `S3_ENDPOINT_URL` vacío → AWS S3 real (ya preparado en `core/spark.py`) |
| ⬜ | Terraform con LocalStack en CI (`terraform plan` sin coste) |
| ⬜ | Variante **Databricks**: notebook/job que lee el mismo bronze; Delta Lake en lugar de Parquet 🔬 |
| ⬜ | Tabla Delta / Iceberg en local para demostrar MERGE y time travel |
| ⬜ | Diagrama de arquitectura local vs. AWS en el README |

## Extras opcionales

| Estado | Tarea |
|---|---|
| ⬜ | Streamlit para exploración ad hoc |
| ⬜ | Agente LLM que responda preguntas sobre el warehouse (solo lectura sobre gold) |
| ⬜ | MQTT / streaming cuando haya una fuente que emita en continuo (fuera de v1) |
| ⬜ | Traducción del README al inglés |

---

## Riesgos conocidos

- **MinIO** dejó de publicar imágenes Docker en 2025. Se usa `pgsty/minio` (build comunitario). Alternativas S3-compatibles: RustFS, SeaweedFS, Garage.
- **Open-Meteo** son datos de modelo (CAMS), no de estación: útiles como referencia y para el Plan B, no como verdad de campo.
- **RAM**: el stack completo usa ~5-6 GB. Con 16 GB va bien; WSL limitado a 10 GB en `.wslconfig`.
- **REData** devuelve 502 con algunos `geo_ids`; el conector debe reintentar y registrar el error sin romper el resto.
