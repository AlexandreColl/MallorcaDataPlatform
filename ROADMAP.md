# Roadmap

Cada versión es una release en GitHub (`vX.Y.Z`) con su entrada en el [CHANGELOG](CHANGELOG.md).
Cada conector es una rama `feature/connector-<nombre>`, un PR a `develop`, un commit `feat(connector): ...`
y una sección en el README.

Leyenda: ✅ hecho · 🟡 en curso · ⬜ pendiente · 🔬 requiere investigación

---

## Fase 0 · Preparación del equipo y decisiones

| Estado | Tarea |
|---|---|
| ✅ | Nombre del proyecto: **MallorcaDataPlatform** |
| ✅ | Comprobar Docker → **no está instalado** (WSL presente, sin distribución). Ver [docs/setup-windows.md](docs/setup-windows.md) |
| ✅ | WSL2 con Debian 13 (trixie) |
| ⬜ | Docker Engine, git y make dentro de Debian; `.wslconfig` con 10 GB ([guía](docs/setup-windows.md)) |
| ⬜ | Clonar el repo en el sistema de ficheros de Debian (`~/projects`) y GitHub CLI (`sudo apt install gh`) |
| ⬜ | Confirmar **Grafana** como visor principal (implementado como propuesta en v0.1) |
| ✅ | Probar REData con llamadas reales → funciona, Baleares = `geo_ids=8743`, solo granularidad **diaria** |
| ✅ | Probar SOCIB → API abierta, 1.598 fuentes, **estaciones activas en Mallorca** (p. ej. `Mobims_CalaMillor`) |
| ✅ | Probar USGS → **0 eventos** en 12 meses en la zona; sustituir por IGN (ver Fase 4) |
| ⬜ | Crear repo en GitHub, subir `main` y `develop`, activar protección de ramas ([docs/git-workflow.md](docs/git-workflow.md)) |

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
| ⬜ | **Primer `docker compose up` real** en tu equipo y ajustes que salgan |
| ⬜ | Primer push a GitHub, CI en verde, tag `v0.1.0` |
| ⬜ | Captura del dashboard en el README |

## Fase 2 · v0.2.x — Más conectores (uno por PR)

| Estado | Versión | Conector | Notas de la prueba real |
|---|---|---|---|
| ⬜ | v0.2.0 | **REData** (demanda eléctrica Baleares) | `apidatos.ree.es/es/datos/demanda/evolucion?geo_limit=baleares&geo_ids=8743&time_trunc=day`. `frequency: 1d`. El endpoint horario `demanda-tiempo-real` devuelve 400 para Baleares → investigar `balance/balance-electrico` |
| ⬜ | v0.2.1 | **SOCIB** (estaciones meteo, boyas, nivel del mar) | `api.socib.es/data-sources/?instrument_type=Weather Station&is_active=true` (12 activas). Datos reales de estación → base para validar Open-Meteo. Datos en NetCDF/THREDDS: decidir entre API `entries` o OPeNDAP 🔬 |
| ⬜ | v0.2.2 | **IGN** sismicidad (sustituye a USGS) | Catálogo del Instituto Geográfico Nacional, filtrar por bbox de Mallorca. Es una fuente de eventos, no serie temporal: el GapRule no aplica |
| ⬜ | v0.2.3 | **OpenAQ v3** | Requiere `OPENAQ_API_KEY` en `.env`. Comprobar primero si hay estaciones del Govern balear (Bellver, Foners, Sant Antoni…) |
| ⬜ | v0.2.4 | **aqicn** | Requiere `AQICN_TOKEN`. Alternativa a OpenAQ para estaciones reales |
| ⬜ | v0.2.5 | **EMT Palma** (GTFS estático) | Paradas y líneas → dimensión geográfica, no serie temporal. Carga mensual |
| ⬜ | — | Plantilla `make new-connector NAME=x` que genere la carpeta, YAML y test vacíos |
| ⬜ | — | Script `make record-fixtures CONNECTOR=x` para regrabar respuestas reales |

Criterio de "hecho" por conector: YAML con métricas, unidades y rangos · fixtures reales · tests · aparece en Grafana · sección en README · ≤ 1 día de trabajo.

## Fase 3 · v0.3.0 — Detección de anomalías

| Estado | Tarea |
|---|---|
| ⬜ | Interfaz `Detector` reutilizable en `core/anomaly/` (entrada: serie silver; salida: score + etiqueta) |
| ⬜ | Detector estadístico: z-score robusto (mediana/MAD) sobre ventana móvil, por serie |
| ⬜ | Detector Isolation Forest (scikit-learn) multivariable por localidad |
| ⬜ | Tabla `silver.anomalies` (serie, ts, detector, score, umbral, run_id) — **marca, no corrige** |
| ⬜ | Tarea `detect_anomalies` en el DAG tras la carga silver |
| ⬜ | **Plan B**: inyector de fallos en Open-Meteo (picos, congelados, deriva, huecos) para medir precisión/recall de cada detector |
| ⬜ | Panel de anomalías en Grafana (anotaciones sobre las series) |

## Fase 4 · v0.4.0 — Correcciones con fuentes de apoyo

| Estado | Tarea |
|---|---|
| ⬜ | Tabla `silver.corrections`: valor original, valor corregido, método, fuente de apoyo, confianza, run_id |
| ⬜ | Nunca sobrescribir bronze ni silver: la vista gold elige `coalesce(corregido, original)` y lo indica |
| ⬜ | Método 1: interpolación temporal para huecos cortos |
| ⬜ | Método 2: sustitución por fuente de apoyo cercana (p. ej. estación SOCIB ↔ celda Open-Meteo) con sesgo calibrado |
| ⬜ | Confianza según distancia, correlación histórica y longitud del hueco |
| ⬜ | Modelo dbt `fct_observations_corrected` + panel "antes / después" |

## Fase 5 · v0.5.0 — Calidad de ingeniería

| Estado | Tarea |
|---|---|
| ⬜ | Contratos de datos en dbt (`contract: enforced`) y tests de frescura de fuentes |
| ⬜ | Modelos dbt incrementales para `fct_observations` |
| ⬜ | Documentación dbt publicada en GitHub Pages (`dbt docs generate`) |
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
