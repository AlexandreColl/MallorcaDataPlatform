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
| ✅ | Visor principal: la web (v0.9) para el público y **Grafana** para la operación de la plataforma |
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
| ✅ | Captura del dashboard en el README |

## Fase 2 · v0.2.x — Más conectores (uno por PR)

| Estado | Versión | Conector | Notas de la prueba real |
|---|---|---|---|
| ✅ | v0.2.0 | **REData** (sistema eléctrico balear) | Demanda **horaria** con `demanda/evolucion?time_trunc=hour` (rango < 1 mes natural: bloques de 28 días); generación por tecnología y CO₂ solo diarios. `demanda-tiempo-real` no existe para Baleares. Núcleo ampliado: frecuencia por dataset y `TimeWindow.split` |
| ✅ | v0.2.1 | **SOCIB** (estaciones meteo y boya) | THREDDS NCSS en CSV, sin clave (la API REST `entries` exige clave). 4 estaciones activas en Mallorca; despliegue vigente resuelto del catálogo; agregación horaria con el QC de SOCIB (`source_qc`). Mismas métricas que Open-Meteo → comparación estación vs modelo |
| ✅ | v0.2.2 | **IGN** sismicidad (sustituye a USGS) | El catálogo del IGN es un formulario web (ignora los filtros sin sesión) y su GeoJSON solo cubre 30 días: se leen las localizaciones del IGN desde el **FDSN de EMSC** (estándar, sin clave). Zona muy tranquila: 57 sismos del IGN en 2020-2026 incluso ampliando la caja 1° alrededor de la isla. Núcleo ampliado: `frequency: event` (sin regla de huecos, ventanas vacías válidas) y `fct_earthquakes` en gold |
| ✅ | v0.2.3 | **EMT Palma** (GTFS estático) | Feed abierto en el GitHub de EMT (el NAP exige registro). En lugar de una dimensión estática, una serie diaria por parada (autobuses programados y líneas) a partir del calendario y de `frequencies.txt`. Junto con: **robustez** (una fuente caída no para el DAG, reintentos con espera creciente, recuperación de días perdidos, E2E que avisa de APIs caídas) y **dashboard único** con selector de fuentes |
| ✅ | v0.2.4 | **Open-Meteo Marine** (oleaje y mar) | Sin clave. Los 8 puntos de la costa devuelven datos completos y hay histórico. Subclase del conector de Open-Meteo con sus propios puntos de mar (las localidades de la región están en el interior) |
| ✅ | v0.2.4 | **AEMET OpenData** | Clave gratuita en `.env`. Las observaciones horarias solo cubren las últimas horas: se usan los valores climatológicos diarios (33 estaciones). API en dos pasos, máximo 6 meses y 25 estaciones por petición, publicación con 2-3 días de retraso. Núcleo ampliado: `lag_days` y selección por defecto que omite conectores sin su clave |
| ✅ | — | **CTM / TIB** (GTFS de toda la isla) | ZIP de 6,7 MB en una URL estable (`tib.org/documents/20124/478141/ctm-mallorca-es.zip`), CC BY 4.0, nueva versión cada día. 78 rutas (71 de autobús TIB, 3 de tren SFM, el metro y 3 a demanda), 780 paradas en toda la isla, 5.501 viajes. Sin `frequencies.txt`, al contrario que EMT: los servicios por parada y día salen de contar `stop_times` con `calendar` y `calendar_dates`. La lógica GTFS pasa de EMT a `core/connectors/gtfs.py` y la comparten los dos. Prueba real: 763 paradas × 30 días sin huecos; la Estació Intermodal tiene 1.028 pasos al día |
| ✅ | — | **Dataestur** (turismo, SEGITTUR) | API REST en `www.dataestur.es/API-SEGITTUR-v2` (OpenAPI de 124 endpoints; la especificación declara una clave, pero no se exige). Responde xlsx, leído con la librería estándar (sin `openpyxl`). Mensual, con 2-3 meses de retraso. Para Baleares: ocupación hotelera `EOH_PROV_DL` (`Provincia=Illes Balears`; julio de 2026, 2,05 M viajeros), llegadas `FRONTUR_DL` (`CCAA de destino=Balears, Illes`; agosto, 2,6 M turistas), gasto `EGATUR_DL` y pasajeros del aeropuerto `AENA_DESTINOS_DL` (`Aeropuerto AENA=P. Mallorca`; agosto, 4,8 M). Ojo: un filtro mal escrito devuelve 200 con el fichero vacío, no un error, así que el conector exige filas. Núcleo ampliado: `frequency: 1mo` (huecos en meses naturales) y `min_days` (la ejecución diaria relee el último año). Prueba real: diez años en un minuto; faltan abril y mayo de 2020 en FRONTUR y EGATUR. Mart `fct_tourism_monthly` y panel en Grafana |
| ✅ | — | **Reservas hídricas** (Govern, DG Recursos Hídrics) | Hoja ODS mensual con los últimos 13 meses de las 18 masas de agua de Mallorca y PDF con 10 años de la isla (etiquetas de texto, `pypdf`). Los ficheros cambian de nombre cada mes: se buscan por el texto del enlace. Mart `fct_water_reserves_monthly` con la anomalía frente al mismo mes. Otros datos del portal valorados: caudales mensuales de depuradoras (XLS anual), consumo y pérdidas por municipio 2000-2024 (xlsx) y agua desalada por planta 1994-2025 (PDF) |
| ✅ | — | **Calidad del aire de la EEA** (sustituye a OpenAQ) | Servicio de descarga de la EEA, sin clave: búsqueda JSON y un Parquet por estación y contaminante, horario y unas dos horas por detrás del tiempo real. 9 estaciones oficiales de Mallorca; coordenadas de OpenAQ, porque los metadatos de la EEA no las traen para España. OpenAQ se probó con clave: mismas estaciones con un 30 % de las horas y duplicados. Mart `fct_air_quality_model_bias_daily` (modelo CAMS frente a estación) |
| ✅ | — | **OpenAQ v3** (probado, no se integra) | Con clave: 8 estaciones activas en Mallorca, todas de la EEA, pero solo con un 30 % de las horas, y Foners y Bellver duplicados. Sustituido por la descarga directa de la EEA (fila anterior) |
| ✅ | — | **aqicn** (probado, no se integra) | Con token: en Mallorca hay 7 estaciones, todas de la red del Govern y atribuidas a la EEA (Foners, Bellver, Hospital Joan March, Sant Joan de Déu, Alcúdia, S'Albufera y Sa Pobla). Solo da la última hora, sin histórico, y como subíndices AQI de EE. UU., no como concentraciones. La previsión diaria (O₃, PM10, PM2.5, UV) es de modelo, como la de Open-Meteo. Sirvió para algo: sus coordenadas confirman las del Govern para Sant Joan de Déu (07040006) y Alcúdia (07003004) |
| ✅ | — | **EEA verificados** (E1a, en `eea_air_quality`) | Cada año está en un solo conjunto: los ficheros *up-to-date* solo traen el año en curso y los verificados todos los anteriores desde 2013, en un fichero por punto de muestreo. El conector parte la ventana por años, guarda en bronze solo las filas de la ventana y descarga cada fichero verificado una vez por proceso. Backfill de julio de 2021 a 2025: `fct_air_quality_monthly` es continuo desde 2002 |
| ✅ | — | **GOIB** (histórico de calidad del aire) | API CKAN del catálogo (`package_show`), sin clave, CC BY. 11 estaciones de Mallorca, de 2002 a junio de 2021 en tres ficheros por estación (hasta 2019, 2020 y 2021) con tres formatos distintos. El periodo 1-24 es la hora que empieza en UTC+01, comprobado contra la EEA. Conector de histórico (`enabled: false`, `make backfill`); bronze guarda las líneas de la ventana y el SHA-256 del fichero. Mart `fct_air_quality_monthly` (GOIB + EEA). Prueba real: 4,98 M valores en ~45 min; NO₂ de Foners de 52,7 µg/m³ (2002) a 31,6 (2019) y 24 (2020). Fallos de la fuente resueltos: el histórico de Menut se solapa con su fichero de 2020 y Hospital Joan March trae filas de 2002 sin periodo |
| ✅ | — | `make new-connector NAME=x`: la carpeta de un conector desactivado, con su YAML, un extractor para una API JSON, su README y un test que reproduce las grabaciones y comprueba cada valor contra el YAML |
| ✅ | — | `make record-fixtures CONNECTOR=x`: graba las respuestas reales del `extract` en `tests/fixtures/` con un `recorded.json`, y `RecordedHttp` las reproduce sin red (una petición no grabada falla). Probado con Open-Meteo (1.440 valores) y REData (35) |
| ✅ | — | SOCIB: histórico por ficheros mensuales (`L1/<año>/..._<año>-<mes>.nc`, uno por mes y despliegue) para los días anteriores al `latest` (`max_days` 366, `make backfill`), y oleaje de las dos boyas activas (bahía de Palma y Portocolom: altura significativa y máxima). Agosto de 2026 cargado del archivo: 744 horas por estación y métrica |
| ✅ | — | Boyas de SOCIB frente al modelo de oleaje (Open-Meteo Marine en el punto más cercano), hora a hora: `fct_wave_model_comparison_hourly`, `agg_wave_model_bias_by_buoy`, `GET /v1/sea/model-bias` y una tabla en la web. Bahía de Palma: 2.498 horas, r = 0,80, el modelo da un 40 % más de ola con mar en calma |
| ✅ | — | Open-Meteo: histórico desde 2017 (`make backfill`, `max_days` 366). La calidad del aire sale de la misma API (CAMS desde 2013) y la meteorología del archivo de las previsiones (`historical-forecast-api`), igual hora a hora que la serie en vivo desde el 16-11-2022 y ERA5 antes, para comparar las estaciones de SOCIB y la EEA con el modelo en todo su histórico |
| ✅ | — | **REDMAR** (mareógrafos de Puertos del Estado, `redmar`) | Sustituye a los de SOCIB: sus carpetas `sea_level` de Mallorca están vacías desde 2024 y los `tide_gauge` de Porto Cristo, Colònia de Sant Pere y Sa Rápita acaban en 2019-2020. THREDDS de Puertos del Estado sin clave: un NetCDF por día a 2 Hz desde 2009 en Palma (3851) y Alcúdia (3853). OPeNDAP en texto con `stride` 120 (un valor por minuto, ~60 KB por día) y media horaria de los minutos con bandera buena. Nivel sobre el cero del puerto (~4,2 m). En 2026 faltan unas 6 horas de cada 24, las mismas en los dos |
| ✅ | — | **Viviendas turísticas** (INE, estadística experimental, `ine_tourist_housing`) | API Tempus sin clave, tabla 39363: viviendas, plazas y plazas por vivienda de cada municipio desde agosto de 2020. La tabla es nacional (44 MB en seis años): un filtro `tv=19:<id>` por municipio la deja en 300 KB para los 53 de Mallorca. Dos recuentos al año en meses que han cambiado (febrero y agosto hasta 2024, mayo y noviembre desde entonces), así que `frequency: event`, sin regla de huecos. Mart `fct_tourist_dwellings` (cambio frente al recuento anterior y viviendas por 1.000 habitantes del padrón), `GET /v1/tourism/dwellings` y una capa en el mapa de Movilidad. Prueba real: 2.067 valores; la isla pasa de 20.196 viviendas en agosto de 2020 a 14.756 en mayo de 2026 (−27 %), Pollença tiene 132 por 1.000 habitantes y Palma, 1,2 |
| ✅ | — | **BiciPalma** (bici pública de Palma, `bicipalma`) | Primera fuente en vivo. El GBFS 2.3 de Nextbike para el sistema `nextbike_ea` (CC0, sin clave) no está enlazado en ninguna parte: el código sale de la API en vivo de Nextbike. CityBikes lee ese mismo feed (sus `uid` son los `station_id` de GBFS), así que no sirve de respaldo. Solo hay estado actual: el DAG `live_poll` guarda `station_status` cada 5 minutos y `station_information` cada hora en bronze, sin Spark (2 s y 75 MB por sondeo), y el conector diario resume las instantáneas por estación y hora ([ADR 0026](docs/adr/0026-fuentes-en-vivo-sin-historico.md)). `last_reported` es el mismo en todas las estaciones (el sello del feed) y en 22 de las 106 bicis más anclajes no suman la capacidad, así que la ocupación divide entre los dos. Marts `fct_bike_stations_hourly` y `fct_bike_stations_daily`, `GET /v1/mobility/bike-stations` y `/bikes/hourly`, una capa en el mapa de Movilidad y un panel en Grafana. Prueba real: 581 bicis libres a media tarde (23 % eléctricas); entre 9 y 19 estaciones se quedan sin bicis en algún momento de cada hora |
| ✅ | — | **Temperatura del mar por satélite** (NOAA OISST v2.1, `noaa_oisst`) | ERDDAP de NOAA CoastWatch sin clave, en CSV: una caja de 3 × 5 celdas de 0,25° con las celdas de mar más cercanas a los 8 puntos de Open-Meteo Marine. Producto definitivo desde 1981 (16 días de retraso) y provisional (1 día) como dos métricas; los 1.196 días que faltan en el eje de ERDDAP (sobre todo 1992-1998) salen de la copia de NOAA PSL por OPeNDAP. Gold: climatología 1991-2020 por día del año, anomalía, olas de calor marinas de Hobday et al. (2016) con islas y huecos (`fct_marine_heatwaves`, con la categoría de 2018) y el satélite frente al modelo. `GET /v1/sea/temperature/daily`, `/monthly` y `/v1/sea/heatwaves`, un panel en Clima y agua y dos en Grafana. Prueba real: 16.507 días en 8 puntos; la anomalía media pasa de −0,48 °C en los ochenta a +1,05 °C desde 2020 y la ola de 2026 frente a Palma dura 131 días |
| ✅ | — | **Cruceristas** (puertos de la APB, dataset `cruises` de `dataestur`) | La APB solo publica sus estadísticas como una imagen PNG por puerto y mes (con base/tránsito, pero haría falta OCR), y la ficha de datos.gob.es enlaza a una sede que bloquea los scripts (Cloudflare). Dataestur sirve el tráfico portuario de Puertos del Estado (`PUERTOS_DL`, `Autoridad portuaria=BALEARES`): mensual desde 2005, cruceristas, escalas y pasajeros totales de los cinco puertos juntos (Palma, unos dos tercios). Coincide con la APB (julio de 2024: 338.252 frente a 338.244). Son pasajeros declarados por escala, sin método publicado (la prensa dice que a menudo es la capacidad). `first_month` por dataset: FRONTUR y EGATUR responden 500 antes de 2016. Ibestat solo tiene una encuesta anual y las escalas previstas solo están en un visor interno del puerto. Gold, API, panel web y de Grafana |

Criterio de "hecho" por conector: YAML con métricas, unidades y rangos · fixtures reales · tests · aparece en Grafana · sección en README · ≤ 1 día de trabajo.

Otras fuentes valoradas (2026-10-27) y por qué no son conectores:

- **Smart Office Palma**: enlaza al GTFS de EMT, que ya se lee de su GitHub.
- **IDEmallorca** (Consell de Mallorca, INSPIRE): capas geográficas WMS/WFS, no series temporales. Útil como dimensión (límites municipales para el mapa), no como conector.
- **datos.gob.es**: catálogo nacional de metadatos; sirve para descubrir conjuntos, los datos están en cada fuente.
- **Meteosource**: comercial y con clave; no aporta nada que no den Open-Meteo y AEMET.

Fuentes posibles (probadas el 2026-11-26 con llamadas reales, aún sin conector):

| Estado | Fuente | Prueba real | Dashboard | Qué aporta |
|---|---|---|---|---|
| ⬜ | **Paro registrado por municipio** (SEPE) | Un CSV por año (`Paro_por_municipios_<año>_csv.csv`, latin1, `;`), mensual, con sexo, edad y sector; los valores bajos llegan como `<5`. 67 municipios de Baleares; Palma, 12.571 en enero de 2026 | Turismo y recursos, Movilidad | La estacionalidad del empleo frente a turistas y demanda eléctrica, y el paro por habitante en el mapa |
| ⬜ | **Polen, polvo sahariano y UV** (Open-Meteo, API de calidad del aire) | `olive_pollen`, `grass_pollen`, `dust` y `uv_index` responden (a 0 en noviembre); falta ver desde cuándo hay histórico | Tiempo y entorno, Operación | Unas líneas en el YAML de `open_meteo`; el polvo explica parte de los picos de PM10 que marcan los detectores |
| ✅ | **BiciPalma en vivo** (GBFS de Nextbike; CityBikes lee el mismo feed) | `gbfs.nextbike.net/maps/gbfs/v2/nextbike_ea/` (CC0), bicis libres y huecos por estación, sin histórico | Movilidad | Hecho: conector `bicipalma` con un sondeo cada 5 minutos que aterriza en bronze ([ADR 0026](docs/adr/0026-fuentes-en-vivo-sin-historico.md)), primer paso del extra de streaming |
| 🔬 | **Demanda en tiempo real de Baleares** (REE Visiona) | El servicio `WSvisionaMovilesBalearesRest` responde pero rechaza todos los códigos de curva (`MALLORCA`, `BALEARES`…). Alternativa: ESIOS, con token, que además da el flujo del enlace con la Península | Turismo y recursos | Demanda cada 10 minutos y mezcla de generación, frente a la horaria de REData |
| 🔬 | **Calidad de las aguas de baño** (EEA, Directiva de aguas de baño) | DiscoData devolvió 502 el día de la prueba | Clima y agua | Clasificación anual de cada playa de la isla |

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
| ✅ | Seis dashboards temáticos (Inicio, Turismo y recursos, Clima y agua, Movilidad, Tiempo y entorno, Operación) enlazados entre sí, con `fct_resources_monthly` (anomalías frente al mismo mes) y un exposure por dashboard; diez años de AEMET y REData cargados con `make backfill` |

## Fase 3 · v0.3.0 — Detección de anomalías

| Estado | Tarea |
|---|---|
| ✅ | Interfaz `Detector` reutilizable en `core/anomaly/` (entrada: serie silver; salida: score + etiqueta): pandas por serie, repartida con `applyInPandas` |
| ✅ | Detector estadístico: z-score robusto (mediana/MAD) sobre ventana móvil, por serie; 7 días en series horarias y 31 en diarias |
| ✅ | Detector Isolation Forest (scikit-learn) multivariable por localidad: valor, cambio, valores seguidos iguales y distancia al valor habitual a esa hora; 49 % de picos y 52 % de congelados (el z-score, 0 %), precisión 85 % |
| ✅ | Tabla `silver.anomalies` (serie, ts, detector, score, umbral, run_id) — **marca, no corrige** |
| ✅ | Tarea `detect_anomalies` en el DAG tras la carga silver (`all_done`); repuntúa los últimos 14 días y es idempotente |
| ✅ | **Plan B**: inyector de fallos en Open-Meteo (picos, congelados, deriva, desfase horario) para medir precisión/recall de cada detector: `make evaluate` y `quality.anomaly_evaluations`. Z-score: 90 % de picos, 22 % de derivas, 0 % de congelados, precisión 80 % |
| ✅ | Benchmark más realista: además del modelo, estaciones reales de SOCIB y de la EEA, cada fuente por separado, y congelados y desfases de reloj en toda la estación a la vez. En las estaciones la precisión del residuo y de la votación baja al 62-74 % y el desfase se detecta un 29-36 % de las veces |
| ✅ | Detector estacional `seasonal_residual` para el desfase horario (reloj o zona horaria): el nivel y el cambio de cada hora frente a la misma hora de los días de alrededor. Del 6 % al 61 % de desfases, con un 81 % de precisión |
| ✅ | Votación `vote` medida con el benchmark: la unión del residuo estacional y el bosque (98 % de picos, 50 % de congelados, 61 % de desfases, 81 % de precisión). Añadir el z-score solo resta precisión y exigir dos votos se deja la mitad de los fallos |
| ✅ | Anomalías como anotaciones de Grafana sobre las series: en el explorador de Tiempo y entorno (la métrica y las entidades elegidas), en el NO₂ de las estaciones (desactivada por defecto: nueve estaciones) y en el antes y después de Operación. Las horas anómalas seguidas de una serie forman una sola banda, con el rango de valores y el valor esperado |

## API REST

| Estado | Tarea |
|---|---|
| ✅ | API de solo lectura con FastAPI sobre los marts con contrato: salud, fuentes, observaciones y anomalías paginadas, reservas, acuíferos y marts mensuales; rol `api_reader`, imagen propia, tests unitarios e integración en CI, y comprobación en el E2E |
| ✅ | `GET /v1/corrections`: las correcciones propuestas de las estaciones (`gold.fct_observations_corrected`), filtrables por fuente, estación, método y rango |
| ✅ | Caché de una hora de los marts que cambian una vez al día (con `ETag` y 304) y límite de 300 peticiones por minuto y cliente (429 con `Retry-After`), en la memoria de cada worker y sin Redis ([ADR 0023](docs/adr/0023-cache-y-limite-en-el-proceso-de-la-api.md)) |
| ✅ | `GET /v1/observations/export`: una serie en CSV (en streaming desde un cursor del servidor) o Parquet (zstd), hasta 366 días y un millón de valores, enlazada desde el explorador de la web |

## Fase 4 · v0.4.0 — Correcciones con fuentes de apoyo

| Estado | Tarea |
|---|---|
| ✅ | Tabla `silver.corrections`: valor y calidad originales, valor corregido, método, fuente de apoyo y su sesgo, confianza, run_id (`core/corrections/`, tarea `correct_values` del DAG tras la detección, recalcula los últimos 14 días) |
| ✅ | Nunca sobrescribir bronze ni silver: `gold.fct_observations_corrected` pone el original y el corregido lado a lado, y `value` es `coalesce(corregido, original)` con `is_corrected` |
| ✅ | Método 1: interpolación temporal para huecos de hasta 3 horas |
| ✅ | Ajuste por altitud: el sesgo de la fuente de apoyo, calibrado por hora del día, recoge la diferencia de altura entre estaciones (la presión de Parc Bit está 14 hPa por debajo de la de la boya), y el modelo se compara con cada estación a su altura (gradiente de 6,5 °C/km entre la estación y la celda del modelo): el error medio de las 29 estaciones de AEMET con altura baja de 1,40 a 0,99 °C, y la Serra d'Alfàbia (996 m por encima de su celda) pasa de +6,0 a −0,4 °C |
| ✅ | Método 2: la serie de la misma métrica mejor correlacionada a menos de 30 km (otra estación de la red o el punto de Open-Meteo, r ≥ 0,6) con su sesgo calibrado por hora del día en los 30 días anteriores |
| ✅ | Confianza según correlación (r²), distancia y longitud del hueco; `make evaluate-corrections` esconde valores limpios en huecos de 1-24 h y mide el error de cada método: 0,26 °C en una hora, 1,35 °C en 24 h con apoyo frente a 2,19 sin su sesgo |
| ✅ | Modelo dbt `fct_observations_corrected` y paneles en Operación: correcciones por día y método, antes y después de la serie elegida y últimas correcciones |
| ✅ | Método 3, **perfil semanal** de la propia estación (cada hora local de laborables y de fines de semana, al nivel de los dos lados del hueco) para el NO₂ y el CO, que casi nunca tienen un apoyo con r ≥ 0,6: en huecos de 24 h, 3,3 µg/m³ de error frente a 4,7 de una recta en el NO₂ y 77 frente a 168 en el CO |
| ✅ | PM10 y PM2.5 con el modelo CAMS aunque su r no llegue a 0,6 (`support.backtest`): el apoyo se prueba en huecos de 24 h cortados del histórico de la estación y se usa si se equivoca menos que una recta, en huecos de 12 h o más. Un sesgo por día de la semana no mejoraba al de cada hora, y la r después del sesgo apenas sube, de 0,18-0,59 a 0,21-0,60. En 28 días, PM10 corrige 765 de 960 horas en huecos de 24 h (antes 279) y PM2.5 208 de 240 (antes ninguna), entre un 8 y un 41 % por debajo de una recta |

## Fase 5 · v0.5.0 — Calidad de ingeniería

| Estado | Tarea |
|---|---|
| ✅ | Linaje con **OpenLineage**: las tareas del DAG declaran sus datos (assets) y el proveedor de Airflow los envía; dbt corre como `dbt-ol` (linaje por modelo y por columna, colgado de la tarea). Marquez opcional (`COMPOSE_PROFILES=lineage`) con un solo grafo de la ingesta a gold |
| ✅ | Alertas de Grafana provisionadas (`dashboards/provisioning/alerting`): ingesta fallida, fuente activa sin ejecución correcta en 36 h y regla de calidad que pasa de verde a rojo, con un panel de alertas en Operación y avisos opcionales a **Telegram** (punto de contacto provisionado solo si `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` están en el `.env`) |
| ⬜ | Probar el envío real de las alertas a Telegram con un bot propio (probado sin token, con un token falso y al quitarlo; falta un mensaje real) |
| ✅ | Cobertura de tests ≥ 80 % en `core/` (84 %, ramas incluidas): el CI falla por debajo, y el informe HTML y el badge del README se publican en GitHub Pages |

## Fase 6 · v1.0.0 — Puente a la nube (los huecos del CV)

| Estado | Tarea |
|---|---|
| ✅ | **Terraform** para AWS (`infra/terraform`): S3 (bronze, silver y resultados, privados, cifrados, solo TLS, con versionado y ciclo de vida), IAM de mínimo privilegio (roles pipeline y analyst), Glue Catalog con *partition projection* sobre el layout de Spark, Athena con límite por consulta y presupuesto de 2 USD. Sin desplegar: sin coste |
| 🟡 | Mismo código, otro perfil: `terraform output pipeline_env` da las variables para S3 real, con el rol del pipeline. Bronze y Spark escriben con credenciales temporales del rol (`S3_CREDENTIALS=role`, probado en local contra el STS de MinIO con un usuario de la misma política). Falta llevar el warehouse a Athena (`dbt-athena`) |
| ✅ | Terraform en CI sin coste: `fmt`, `validate`, tflint (ruleset de AWS) y `terraform test` con `mock_provider` (13 tests). LocalStack no hace falta: su edición gratuita no tiene Glue ni Athena |
| ✅ | Variante **Databricks** en Free Edition ([databricks/](databricks/README.md), [ADR 0025](docs/adr/0025-variante-en-databricks-free-edition.md)): un Lakeflow Job descrito como bundle que extrae Open-Meteo y la EEA con los mismos conectores a un Volume de Unity Catalog, carga bronze con Auto Loader, silver con un `MERGE` en la clave y cuatro tablas gold, entre ellas el sesgo del modelo CAMS frente a las estaciones. Catálogo `mallorca` con un esquema por capa y `GRANT` de lectura sobre gold. Ejecutado en serverless (entorno 6, Python 3.12): unos 2 minutos por ejecución |
| ✅ | Silver como tabla **Delta Lake** en MinIO: `MERGE` por la clave, historial de versiones, *time travel* y *Change Data Feed* (`make silver-changes`), una partición por fuente con `OPTIMIZE … ZORDER BY (ts)` y `VACUUM`, conversión y reescritura del lake Parquet (67.000 ficheros → 12) y Glue/Athena leyendo el log. Iceberg aún no tiene runtime para Spark 4.2 |
| ✅ | Diagrama de arquitectura local frente a AWS ([infra/terraform/README.md](infra/terraform/README.md)) |

## Fase 7 · Hacia arquitectura de datos

Lo que convierte el proyecto en un caso de arquitectura: decisiones registradas, un modelo de datos explícito y un
despliegue real con su coste medido.

| Estado | Tarea |
|---|---|
| ✅ | **Trade-offs, costes y escalado** en [docs/architecture.md](docs/architecture.md#5-trade-offs-costes-y-escalado): volumen medido, qué se paga por cada decisión y cuándo revisarla, qué se rompe a 10× y 100× y costes estimados en AWS |
| ✅ | **ADRs** en [docs/adr](docs/adr/README.md): 23 decisiones con su estado y su fecha, la plantilla y el índice. Incluyen las sustituidas y las rechazadas (silver en Parquet → Delta, USGS → IGN, OpenAQ → EEA) y una sección "Cuándo revisarla" en cada una |
| ✅ | **Modelo de datos documentado** ([docs/data-model.md](docs/data-model.md)): modelo conceptual, silver largo con su clave y su significado, estrella de gold con el grano y el tipo de cada hecho, dimensiones compartidas con su política de historia (snapshot SCD2 de ubicaciones), contratos en tres fronteras, convenciones de tiempo y nulos, frescura por fuente y reglas de evolución del esquema. En dbt: `dim_metrics` (una unidad por métrica como clave primaria), contrato en `dim_locations` y `dim_date` desde 2002 para cubrir todo el histórico |
| ✅ | **Frontal web** (`web/`, http://localhost:3002): portada con cinco cifras clave frente a lo normal de cada mes, mapa de estaciones, puntos de modelo y paradas, y estado de las fuentes. React + Vite + ECharts + MapLibre, solo lee la API ([ADR 0019](docs/adr/0019-frontal-web-sobre-la-api.md)) |
| ✅ | Seis dashboards en la web con un menú lateral (inicio, turismo y recursos, clima y agua, movilidad, tiempo y entorno, operación), modo claro y oscuro con botón, logo con la silueta de la isla y diez endpoints nuevos en la API |
| ✅ | Tendencias de 12 meses y correlaciones de Pearson (con y sin el ciclo anual) en turismo y recursos, temperatura por zonas interpolada y mapa de calidad del aire más grande |
| ✅ | Avisos de AEMET por zona (conector `aemet_warnings`) y población por municipio del padrón del INE (`ine_population`, frecuencia anual `1y`), con su mapa en la web |
| ✅ | Diagrama de arquitectura en claro y oscuro generado desde código, y capturas de la web en el README (`make screenshots`) |
| ✅ | Movilidad: un solo mapa con las paradas de cada red sobre los municipios, un selector para colorearlos (densidad, servicio por habitante, crecimiento o sin color) y la ficha del municipio o de la parada al pulsar |
| ✅ | Movilidad: línea de tendencia sobre las barras de la población de Mallorca desde 1996, con el crecimiento medio anual (ajuste exponencial) |
| ✅ | Tiempo y entorno: temperatura por zonas suave, una imagen interpolada píxel a píxel (unos 160 m) en lugar de celdas cuadradas, recortada con los límites municipales |
| ✅ | Tiempo y entorno: temperatura corregida por la altitud (gradiente de 6,5 °C/km con el relieve abierto de Mapzen Terrain Tiles), isotermas cada grado y la temperatura y la altura bajo el cursor |
| ✅ | Movilidad: mapa, tabla y gráfico enlazados por municipio (pulsar en uno lo resalta en los otros), población de cualquier municipio y tendencia en uno o dos tramos con la proyección a 2030 y su intervalo del 95 % |
| ✅ | Tiempo y entorno: elegir el día de la temperatura por zonas (`date` en `/v1/weather/stations`) |
| ✅ | Movilidad: recorridos de las líneas desde `shapes.txt` del GTFS, en su propia tabla (`silver.routes`, `dim_routes`), con las salidas por línea y día (`scheduled_trips`) |
| ✅ | Conector del **Indicador de Presión Humana** del Ibestat (`ibestat_iph`, personas presentes en Mallorca cada día desde 1997) y su gráfico en Movilidad |
| ✅ | Explorador de series en la web: fuente, entidad y métrica día a día, con su completitud, sus valores sospechosos y sus anomalías (`/v1/series`, `/v1/series/daily`); las correcciones siguen en Operación |
| ✅ | Nombres de las paradas y estaciones en silver (`silver.entities`): la web ya no enseña `stop_452` ni `B228` |
| ✅ | Nombres en Grafana (mapas, tablas, leyendas, anotaciones y selectores) y en los puntos de Open-Meteo (`label` en el YAML) |
| ✅ | **Web en castellano, catalán e inglés** ([ADR 0024](docs/adr/0024-la-web-en-tres-idiomas.md)): idioma en la URL (`/ca/movilidad`), selector, diccionarios tipados y formatos con `Intl` todos los textos de las siete páginas y el catálogo de fuentes por idioma en la API (`Accept-Language`, caché por idioma) |
| ✅ | **Gobierno del dato** ([docs/data-governance.md](docs/data-governance.md), [ADR 0020](docs/adr/0020-gobierno-del-dato-en-el-catalogo-de-fuentes.md)): cada fuente tiene en el catálogo su dueño, su licencia con el enlace a las condiciones, el acceso, si tiene datos personales, la clasificación, el ciclo de vida y un SLA acordado (antigüedad máxima del último dato y cargas correctas en 7 días). `source_health` lo evalúa y la API, la web y una alerta de Grafana lo enseñan, en lugar de umbrales fijos |
| ✅ | **Arranque incremental** ([ADR 0021](docs/adr/0021-solo-los-dias-que-faltan.md)): el DAG corre solo cada día y, tras un reinicio, una vez; cada conector descarga solo los días que ninguna carga correcta ha cubierto (`only_missing`) y se salta si no falta ninguno |
| ⬜ | **Despliegue real en AWS**, puntual: `terraform apply`, silver en S3 leída por Athena, Spark con el rol IAM, coste real anotado y `terraform destroy` |
| ⬜ | Gold en Athena con `dbt-athena` (quita la copia de silver en Postgres) |
| ⬜ | Segundo motor (BigQuery sandbox) solo si las ofertas objetivo lo piden, con su ADR 🔬 |

## Extras opcionales

| Estado | Tarea |
|---|---|
| ⬜ | Streamlit para exploración ad hoc |
| ⬜ | Agente LLM que responda preguntas sobre el warehouse (solo lectura sobre gold) |
| 🟡 | MQTT / streaming cuando haya una fuente que emita en continuo (fuera de v1). Primer paso hecho con BiciPalma: un sondeo cada 5 minutos que aterriza en bronze y el conector diario que lee de ahí ([ADR 0026](docs/adr/0026-fuentes-en-vivo-sin-historico.md)). Un consumidor MQTT ocuparía el lugar del sondeo y escribiría las mismas instantáneas |
| ✅ | Traducción del README al inglés ([README.en.md](README.en.md)), enlazada desde la cabecera de los dos |

---

## Riesgos conocidos

- **MinIO** dejó de publicar imágenes Docker en 2025. Se usa `pgsty/minio` (build comunitario). Alternativas S3-compatibles: RustFS, SeaweedFS, Garage.
- **Open-Meteo** son datos de modelo (CAMS), no de estación: útiles como referencia y para el Plan B, no como verdad de campo.
- **RAM**: el stack completo usa ~5-6 GB. Con 16 GB va bien; WSL limitado a 10 GB en `.wslconfig`.
- **REData** devuelve 502 con algunos `geo_ids`; el conector debe reintentar y registrar el error sin romper el resto.
