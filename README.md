# Mallorca Data Platform

[![CI](https://github.com/AlexandreColl/MallorcaDataPlatform/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/AlexandreColl/MallorcaDataPlatform/actions/workflows/ci.yml)
[![E2E](https://github.com/AlexandreColl/MallorcaDataPlatform/actions/workflows/e2e.yml/badge.svg)](https://github.com/AlexandreColl/MallorcaDataPlatform/actions/workflows/e2e.yml)
[![Coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Falexandrecoll.github.io%2FMallorcaDataPlatform%2Fcoverage%2Fbadge.json)](https://alexandrecoll.github.io/MallorcaDataPlatform/coverage/)
[![dbt docs](https://img.shields.io/badge/dbt_docs-lineage-FF694B)](https://alexandrecoll.github.io/MallorcaDataPlatform/)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Airflow](https://img.shields.io/badge/airflow-3.4-017CEE)
![Spark](https://img.shields.io/badge/pyspark-4.2-E25A1C)
![dbt](https://img.shields.io/badge/dbt-1.12-FF694B)

[English](README.en.md) · **Español**

Plataforma de datos **modular y 100 % local** sobre datos abiertos reales de Mallorca.
Un `docker compose up` levanta Airflow, PySpark, MinIO (S3), PostgreSQL, dbt y Grafana; un DAG con
parámetros extrae las fuentes elegidas, comprueba su calidad y lo deja todo listo para analizar.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/web/inicio-oscuro.png">
  <img alt="Inicio de la web: cinco cifras clave frente a lo normal de cada mes y el mapa de estaciones de Mallorca" src="docs/img/web/inicio.png">
</picture>

```json
{"connectors": ["open_meteo"], "days": 30, "region": "mallorca"}
```

## Arquitectura

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/architecture-dark.svg">
  <img alt="Arquitectura: 19 fuentes abiertas entran por conectores en Python a bronze (MinIO); PySpark las normaliza en silver (Delta Lake y Postgres); Python marca anomalías y propone correcciones; dbt construye gold en Postgres; la API, la web y Grafana lo sirven. Airflow orquesta cada paso." src="docs/img/architecture.svg">
</picture>

El diagrama se genera con `node scripts/architecture/diagram.mjs` (versión clara y oscura, logos de Simple Icons).

Airflow orquesta cada flecha con el DAG `mallorca_pipeline`: una tarea `ingest` por conector, y después
`detect_anomalies`, `correct_values` y `dbt_build`. Bronze vive en MinIO; silver, en una tabla Delta de MinIO y en
Postgres; gold, en Postgres.

| Capa | Dónde | Contenido |
|---|---|---|
| **bronze** | `s3://bronze/<fuente>/<dataset>/window=<desde>_<hasta>/payload.json` | Respuesta de la API sin tocar. Clave determinista + versionado del bucket: relanzar no duplica y el crudo anterior se conserva |
| **silver** | tabla Delta `s3://silver/observations` (una partición por fuente, `source=…`) y `silver.observations` | Esquema común: `source, entity, metric, ts, value, unit, quality, lat, lon` (+ `quality_reasons`, `run_id`, `ingested_at`). Cada carga es una versión de la tabla Delta: historial y *time travel* ([abajo](#silver-en-delta-lake)) |
| **gold** | esquema `gold` (dbt: staging → intermediate → marts, [detalle](dbt/README.md)) | hechos incrementales (`fct_observations`, `agg_daily_metrics`), marts por dominio (tiempo diario, mar, electricidad, bus, calidad del aire, sismos) y salud de las fuentes |

### Decisiones de diseño

El caso completo, con el contexto, las restricciones, cada decisión con su porqué, lo que se descartó y lo que cuesta:
[docs/architecture.md](docs/architecture.md). Allí está también qué se rompe primero a 10× y 100× y cuánto costaría
en AWS ([trade-offs, costes y escalado](docs/architecture.md#5-trade-offs-costes-y-escalado)). Cada decisión tiene
su ADR en [docs/adr](docs/adr/README.md), incluidas las que se sustituyeron o se rechazaron. El modelo de datos (silver,
la estrella de gold, el grano de cada hecho y los contratos) está en [docs/data-model.md](docs/data-model.md). El
dueño, la licencia, el acceso y el SLA de cada fuente están en [docs/data-governance.md](docs/data-governance.md). En
resumen:

- **Núcleo fijo, conectores intercambiables.** El núcleo solo conoce `extract()` y `normalize()` (y el opcional `describe()`, que pone nombre a las paradas y estaciones).
  Un conector es una carpeta con su YAML, su extractor y sus tests con respuestas grabadas.
- **Idempotencia en todas las capas**: ventanas de días completos (siempre la misma petición), claves
  deterministas en bronze, `MERGE` en la tabla Delta de silver y `INSERT … ON CONFLICT … WHERE IS DISTINCT FROM`
  en Postgres: las filas que no cambian no se reescriben. El E2E de CI lanza el DAG dos veces y comprueba que no cambia el número de filas.
- **Una fuente caída no para el resto.** Cada conector es una tarea independiente con reintentos (2, 4 y 8 min);
  si al final falla, dbt reconstruye gold con lo que sí cargó y el fallo queda en `ops.ingestion_runs` con el tipo de
  error. Si lo que falla es la fuente (no responde, da 5xx o aún no ha publicado), la tarea se omite en vez de fallar
  y la ejecución queda como `unavailable`, aparte de los fallos propios (`failed`)
  ([ADR 0022](docs/adr/0022-fuente-caida-no-es-un-fallo.md)).
  La siguiente ejecución de esa fuente **recupera los días perdidos**: su ventana empieza el día después de
  su última carga correcta (hasta `catch_up_days`; un hueco más largo, en ejecuciones extra hasta `recover_days`
  donde la API guarda histórico), y no vuelve a pedir los días que ya cargó (`only_missing`). El E2E distingue una API caída o una fuente que ha dejado de
  publicar (`SourceNotUpdatedError`: aviso) de un fallo real (error).
- **Marcar ≠ corregir.** Las reglas de calidad etiquetan (`ok` / `suspect` / `missing`) y explican
  (`quality_reasons`), pero nunca modifican el valor. Las correcciones van aparte, en `silver.corrections`, y gold
  muestra los dos valores ([abajo](#correcciones-con-fuentes-de-apoyo)).
- **Local primero, nube después.** MinIO habla S3 y Spark usa S3A: pasar a AWS es cambiar el endpoint y las credenciales.
  Con `S3_CREDENTIALS=role`, bronze y Spark escriben con credenciales temporales de un rol de privilegio mínimo,
  también en local contra el STS de MinIO ([detalle](infra/terraform/README.md)).

## Puesta en marcha

Requisitos: Docker Engine con Compose y ~8 GB de RAM libres (Linux, macOS o Windows con WSL2).
Guía para Windows con WSL2 + Debian: [docs/setup-windows.md](docs/setup-windows.md).

```bash
make up                                      # crea .env, construye la imagen y levanta todo
make run CONNECTORS=open_meteo DAYS=30       # dispara el DAG (solo los días que faltan; ONLY_MISSING=false: todos)
make run-local CONNECTORS=open_meteo DAYS=1  # mismo pipeline sin Airflow
make backfill CONNECTORS=aemet START=2016-09-01 END=2026-10-25  # histórico, un run por año
```

| Servicio | URL | Acceso |
|---|---|---|
| **Web** | http://localhost:3002 | la isla en cifras: KPIs, mapa y estado de las fuentes ([abajo](#frontal-web)) |
| Airflow | http://localhost:8080 | sin login (modo demo local) |
| Grafana | http://localhost:3000 | anónimo de lectura · admin/admin |
| MinIO | http://localhost:9001 | minioadmin/minioadmin |
| API REST | http://localhost:8000/docs | lectura pública (rol `api_reader`) |
| PostgreSQL | localhost:5432 | `make psql` |
| Marquez (opcional) | http://localhost:3001 | linaje OpenLineage, con `COMPOSE_PROFILES=lineage` ([abajo](#linaje-con-openlineage)) |

Otros comandos: `make help`.

**Al reiniciar el PC no se pierde ni se repite nada.** Postgres, MinIO, Grafana y los logs viven en volúmenes de
Docker (`make down` los conserva; solo `make clean` los borra). El DAG corre solo cada día (`MDP_SCHEDULE=@daily`):
si el PC estaba apagado, Airflow lanza la ejecución pendiente al arrancar, una vez. Cada conector descarga solo los
días que ninguna carga correcta ha cubierto, desde el primero que falta, y si no falta ninguno ni llama a la fuente
([ADR 0021](docs/adr/0021-solo-los-dias-que-faltan.md)).

## Conectores

| Conector | Estado | Datos | Clave |
|---|---|---|---|
| [open_meteo](connectors/open_meteo/README.md) | ✅ | Calidad del aire (CAMS), con polen de olivo y gramíneas, polvo sahariano y UV, y meteorología, horario, 6 localidades | No |
| [redata](connectors/redata/README.md) | ✅ v0.2.0 | Demanda eléctrica horaria, mix de generación y CO₂ diarios del sistema balear | No |
| [socib](connectors/socib/README.md) | ✅ v0.2.1 | Observaciones reales de 3 estaciones y 1 boya (temperatura, humedad, presión, viento), horarias con QC de la fuente | No |
| [redmar](connectors/redmar/README.md) | ✅ | Nivel del mar horario en los mareógrafos de Palma y Alcúdia de Puertos del Estado (red REDMAR, desde 2009) | No |
| [noaa_oisst](connectors/noaa_oisst/README.md) | ✅ | Temperatura diaria de la superficie del mar por satélite (NOAA OISST v2.1, 0,25°) en 8 puntos de la costa, desde 1981 | No |
| [ign](connectors/ign/README.md) | ✅ v0.2.2 | Sismos localizados por el IGN en Mallorca y el mar que la rodea (magnitud, profundidad, epicentro) | No |
| [emt_palma](connectors/emt_palma/README.md) | ✅ v0.2.3 | Autobuses programados y líneas por parada y día (875 paradas, GTFS estático) | No |
| [open_meteo_marine](connectors/open_meteo_marine/README.md) | ✅ v0.2.4 | Oleaje, temperatura del mar, corrientes y nivel del mar (modelo) en 8 puntos de la costa | No |
| [aemet](connectors/aemet/README.md) | ✅ v0.2.5 | Valores diarios oficiales de 33 estaciones de AEMET en Mallorca (temperatura, lluvia, humedad, viento, sol, presión) | Sí |
| [ctm](connectors/ctm/README.md) | ✅ | Autobuses TIB, tren SFM y metro programados por parada y día en toda la isla (763 paradas, GTFS estático) | No |
| [bicipalma](connectors/bicipalma/README.md) | ✅ | Bicis libres (y eléctricas), anclajes y ocupación de las 106 estaciones de BiciPalma, hora a hora, desde el GBFS del operador sondeado cada 5 minutos | No |
| [dataestur](connectors/dataestur/README.md) | ✅ | Turismo mensual de Baleares: turistas internacionales y gasto, ocupación hotelera, pasajeros del aeropuerto de Palma y cruceristas de los puertos de la APB | No |
| [water_reserves](connectors/water_reserves/README.md) | ✅ | Reservas de agua subterránea de Mallorca por acuífero y de la isla, mensuales (10 años de la isla) | No |
| [goib_air_quality](connectors/goib_air_quality/README.md) | ✅ histórico | NO₂, O₃, PM10, PM2.5, SO₂ y CO horarios de 11 estaciones oficiales de Mallorca, de 2002 a junio de 2021 (catálogo del Govern). Solo con `make backfill` | No |
| [eea_air_quality](connectors/eea_air_quality/README.md) | ✅ | NO₂, O₃, PM10, PM2.5, SO₂ y CO horarios de 9 estaciones oficiales de Mallorca (red del Govern, vía la EEA), verificados desde 2013 | No |
| [aemet_warnings](connectors/aemet_warnings/README.md) | ✅ | Avisos meteorológicos de AEMET (lluvias, tormentas, viento, costeros…) por zona de Mallorca y hora, del nivel 0 al 3 | Sí |
| [ine_population](connectors/ine_population/README.md) | ✅ | Población de los 53 municipios de Mallorca a 1 de enero, por sexo, del padrón del INE (desde 1996) | No |
| [ine_tourist_housing](connectors/ine_tourist_housing/README.md) | ✅ | Viviendas turísticas y plazas de los 53 municipios de Mallorca, dos recuentos al año de la estadística experimental del INE (desde agosto de 2020) | No |
| [sepe_unemployment](connectors/sepe_unemployment/README.md) | ✅ | Paro registrado de los 53 municipios de Mallorca cada mes, por sexo y edad y por sector, del SEPE (desde 2006) | No |
| [nayade](connectors/nayade/README.md) | ✅ | E. coli y enterococos de cada muestra de las 87 aguas de baño de Mallorca en temporada, con el aviso de baño y las restricciones (Náyade, Ministerio de Sanidad, desde 2023) | No |
| [ibestat_iph](connectors/ibestat_iph/README.md) | ✅ | Personas presentes en Mallorca cada día, residentes más visitantes (Indicador de Presión Humana del Ibestat, desde 1997) | No |

### Open-Meteo

Una petición por dataset con todas las localidades de la región. 14 métricas horarias
(PM10, PM2.5, NO₂, O₃, EAQI, polen de olivo y de gramíneas, polvo sahariano, UV, temperatura, humedad, precipitación,
viento, presión). Con `DAYS=1` son 6 × 24 × 14 = 2.016 observaciones. Son datos de modelo, no de estación.

La API de previsión solo sirve 92 días, pero `make backfill CONNECTORS=open_meteo` carga los años anteriores: la
calidad del aire sale del mismo modelo CAMS (desde 2013) y la meteorología del archivo de las mismas previsiones, que
coincide hora a hora con la serie en vivo desde noviembre de 2022 y es el reanálisis ERA5 antes. Así las estaciones
de SOCIB y de la EEA se comparan con el modelo desde 2017, como el histórico de SOCIB. El sesgo cambia de nivel el
16-11-2022, el día que el archivo pasa de ERA5 a las previsiones: en Cala Millor, de −0,92 a −1,54 °C en la
temperatura media diaria.

**Polen, polvo sahariano y UV.** La misma API de CAMS sirve el polvo desde 2018, el polen desde octubre de 2020 (solo
en temporada hasta noviembre de 2023) y el UV desde agosto de 2022; `available_since` evita pedirlos antes. En gold,
`fct_pollen_dust_daily` da el nivel de polen del día con los umbrales de la Red Española de Aerobiología y
`fct_dust_episodes` los **episodios de polvo sahariano**: días seguidos con la media de polvo de la isla en 25 µg/m³
o más, la mitad del límite diario de PM10. Hubo 24 de 2019 a 2026, con 44 días. Durante los 19 que tienen estaciones
de la EEA, su PM10 sube de 20 a 56 µg/m³ de media, y el PM10 de CAMS se queda 5,6 µg/m³ por debajo (32 en el de marzo
de 2025, con 185 µg/m³ de polvo en una hora): los huecos de PM10 que se rellenan con CAMS un día de polvo salen bajos.
El olivo florece de abril a junio con el pico en mayo, y llega al nivel moderado sobre todo en Sóller e Inca, entre
olivares (218 granos/m³ de media un día en Sóller); en Palma casi nunca. Los detectores de anomalías no puntúan
estas métricas: son cero casi siempre y sus picos son el fenómeno. En la web, *Tiempo y entorno* tiene la temporada
de polen, el polvo del último año, los episodios y el polvo en cada estación; en Grafana, el polvo frente al PM10 de
las estaciones y una tabla de episodios. [Detalle y pruebas reales](connectors/open_meteo/README.md).

### Open-Meteo Marine

La misma API con modelos de oleaje y océano en 8 puntos de mar alrededor de la isla: altura, periodo y dirección de
ola, mar de fondo, temperatura del mar, corrientes y nivel del mar. Es una subclase del conector de Open-Meteo que
solo cambia los puntos consultados (las localidades de la región están en el interior). En Grafana, gotas en el mapa
con el color y la altura de ola; el resto de métricas, en el selector.

### AEMET

Valores climatológicos **diarios** de las estaciones oficiales de AEMET en Mallorca (temperatura media, mínima y
máxima, lluvia, humedad, viento, horas de sol y presión). Necesita una API key gratuita en `.env`
(`AEMET_API_KEY`); sin ella el conector queda fuera de la selección por defecto. La API es de dos pasos, acepta
hasta 25 estaciones por petición y publica con 2-3 días de retraso, por eso declara `lag_days: 3`. En Grafana,
iconos de sol y nube en el mapa con el último día publicado.

### AEMET (avisos)

Los avisos de AEMET (Meteoalerta) de las nueve zonas de Mallorca (cinco de tierra y cuatro de aguas costeras),
hora a hora y por fenómeno: lluvias, tormentas, viento, costeros, temperaturas, nieblas, rissagas… El valor es
el nivel: 0 sin riesgo, 1 amarillo, 2 naranja y 3 rojo. Usa la misma clave que `aemet`. Cada emisión de AEMET es
una foto de los avisos en vigor: un aviso que deja de aparecer se ha retirado, sin `Cancel`. Por eso cada hora toma
el nivel de la foto que estaba en vigor. El archivo da las horas pasadas y la última emisión las de hoy y los próximos
días. En gold, `fct_weather_warnings` da un periodo por aviso; en la web, un mapa con las zonas coloreadas por nivel.
[Detalle y pruebas reales](connectors/aemet_warnings/README.md).

### INE (población)

La población de cada municipio de Mallorca a 1 de enero, por sexo, del padrón continuo del INE (tabla 2860, desde
1996; en 1997 no hubo padrón). Es la primera fuente anual: el núcleo gana `frequency: 1y` (huecos contados en años
naturales). Cada ejecución relee los tres últimos años, porque el INE revisa las cifras una vez, y la ventana acaba
350 días antes de ayer, porque las cifras de un año salen a mediados de diciembre. El seed `dim_municipalities`
guarda el límite de cada municipio (IGN, simplificado a unos 150 m). En gold, `fct_population_yearly` añade la
densidad y el cambio frente al padrón anterior; el total de la isla es la suma de sus municipios. En la web, el
dashboard de Movilidad cruza la población con las paradas de cada municipio: Palma tiene 186 pasos programados por
cada 1.000 habitantes en un día laborable y Manacor, 27.
[Detalle y pruebas reales](connectors/ine_population/README.md).

### INE (viviendas turísticas)

Las viviendas turísticas, sus plazas y las plazas por vivienda de cada municipio de Mallorca, de la estadística
experimental del INE que cuenta los anuncios de las principales plataformas de alquiler (tabla 39363, desde agosto
de 2020). La tabla cubre toda España: el conector la filtra a los 53 municipios con un `tv` por municipio, y la
descarga baja de 44 MB a 300 KB. Hay dos recuentos al año, pero sus meses han cambiado (febrero y agosto hasta 2024;
mayo y noviembre desde entonces), así que el conjunto es `frequency: event`: sin regla de huecos y con las demás
reglas de calidad. En gold, `fct_tourist_dwellings` añade el cambio frente al recuento anterior y el peso frente al
padrón. En la web, el mapa de Movilidad tiene una capa más: en mayo de 2026 había 14.756 viviendas turísticas en la
isla (un 27 % menos que en agosto de 2020); Pollença tiene 132 por cada 1.000 habitantes y Palma, 1,2.
[Detalle y pruebas reales](connectors/ine_tourist_housing/README.md).

### SEPE (paro registrado)

Las personas en paro registrado el último día hábil de cada mes en cada municipio de Mallorca, por sexo y edad y
por sector, de los datos abiertos del SEPE (un CSV por año desde 2006, de unos 10 MB con toda España). Bronze guarda
solo las líneas de Baleares de los meses de la ventana, con el SHA-256 del fichero entero. Desde 2022 el SEPE
publica toda cifra de 1 a 4 como `<5`: se guarda como nulo, nunca como 5, y una opción nueva del core por métrica
(`suppressed_below`) evita que las reglas de nulos y de huecos lo cuenten como fallo. Los meses que faltan en el
CSV (mayo a diciembre de 2013 y diciembre de 2020) salen del PDF mensual de la provincia, comprobado fila a fila.
En gold, `fct_unemployment_monthly` y
`fct_unemployment_island_monthly` dan el paro por 1.000 habitantes, el interanual y la anomalía frente al mismo
mes, y `agg_unemployment_seasonality` el paro de invierno frente al de verano: casi un 50 % más en invierno hasta
2019 (1,49) y un 14 % en 2025, tras la reforma laboral de 2022. En la web, Turismo y recursos lo correlaciona con
turistas, aeropuerto y cruceristas, y el mapa de Movilidad tiene una capa de paro por habitante.
[Detalle y pruebas reales](connectors/sepe_unemployment/README.md).

### Ibestat (presión humana)

Las personas presentes en Mallorca cada día: los empadronados, más los visitantes que llegan por puerto o aeropuerto,
menos los residentes que están fuera (Indicador de Presión Humana, conjunto `000011A_000002` de la API eDatos del
Ibestat, desde 1997). La API devuelve un cubo plano. El conector pide solo Mallorca y los días de la ventana, sin
metadatos, en peticiones de un año como máximo. Los días recientes son estimaciones y se revisan, así que cada
ejecución relee 120 días. La ventana acaba 95 días antes de ayer, porque un mes sale a principios del tercer mes
siguiente. En gold, `fct_human_pressure_daily` lo compara con el padrón: el 11 de agosto de 2026 había 1.517.631
personas en la isla, 1,58 por residente. En la web, Movilidad superpone los tres últimos años frente a los
empadronados.
[Detalle y pruebas reales](connectors/ibestat_iph/README.md).

### REData

Red Eléctrica publica el sistema eléctrico balear completo (Mallorca es ~80 % de la demanda). Tres datasets
con granularidad distinta, cada uno con su propia `frequency` para la regla de huecos:

| Dataset | Granularidad | Métricas |
|---|---|---|
| Demanda | horaria (peticiones troceadas en bloques de 28 días) | `electricity_demand` (MWh) |
| Generación | diaria | `generation_<tecnología>` y `generation_total` (MWh) |
| Emisiones | diaria | `co2_emissions` (tCO2eq), `co2_intensity` (tCO2eq/MWh) |

Las series de la API se mapean a métricas en el YAML; una serie nueva (p. ej. una tecnología que aparece en el
mix) genera un aviso en lugar de perderse en silencio. En Grafana: demanda horaria e intensidad de CO₂ en
una gráfica, y el mix por tecnología en la tabla de series.

### SOCIB

Observaciones **reales** de estaciones meteorológicas (ParcBit, Cala Millor, Muro) y de la boya de la Bahía de
Palma, leídas del servidor THREDDS de SOCIB en CSV (sin clave). Los datos llegan cada 1-10 minutos con el QC de
SOCIB por variable; el conector los agrega por hora usando solo las muestras buenas y marca `suspect` las horas
con menos del 50 % de muestras válidas. Las métricas se llaman igual que en Open-Meteo, así que Grafana compara
estación real y modelo en la misma gráfica.

También lee el **oleaje** de las dos boyas activas, la de la bahía de Palma y la de Portocolom: la altura
significativa y la máxima cada media hora, agregadas por hora (`wave_height`, como en Open-Meteo Marine, y
`wave_height_max`). Los días anteriores al fichero `latest` salen de los ficheros mensuales del archivo, uno por mes
y despliegue, así que `make backfill CONNECTORS=socib` carga el histórico: llega a marzo de 2017 en Cala Millor y a
2022 en Platja de Muro; las demás estaciones empiezan en 2025 y 2026.

**Boyas frente al modelo de oleaje**: cada boya se empareja con el punto de Open-Meteo Marine más cercano (a menos
de 2 km) y se comparan las alturas significativas hora a hora (`fct_wave_model_comparison_hourly`, y el resumen
por boya en `agg_wave_model_bias_by_buoy`, `GET /v1/sea/model-bias` y la web). De agosto al 14 de noviembre de 2026:

| Boya | Horas | Boya (media) | Modelo (media) | Sesgo | Error medio | RMSE | r |
|---|---|---|---|---|---|---|---|
| Bahía de Palma | 2.498 | 0,34 m | 0,39 m | +0,05 m | 0,16 m | 0,23 m | 0,80 |
| Portocolom | 361 | 0,86 m | 0,78 m | −0,08 m | 0,18 m | 0,45 m | 0,63 |

En la bahía, con mar en calma (menos de 0,5 m), el modelo da un 40 % más de ola de la que mide la boya: su celda de
unos 5 km se asoma a mar abierto y la boya está en una bahía resguardada. En Portocolom pasa al revés con la mar
pequeña, y el RMSE (0,45 m), muy por encima del error medio, delata unas pocas horas con fallos grandes.

### Mareógrafos (Puertos del Estado)

Los mareógrafos de Palma y Alcúdia de la red REDMAR, leídos del servidor THREDDS de Puertos del Estado sin clave.
Cada día es un fichero NetCDF con el nivel del mar cada medio segundo; el conector pide por OPeNDAP, en texto, un
valor por minuto (unos 60 KB por día en lugar de 5,4 MB) y hace la media horaria de los que la fuente marca como
buenos.

- **El nivel es la altura sobre el cero de cada puerto**, unos 4,2 m. Sirve para seguir la marea y los temporales
  en cada mareógrafo, no para compararlo con el modelo de Open-Meteo Marine, que mide sobre el nivel medio del mar.
- **En 2026 faltan horas enteras**, unas 6 de cada 24 y las mismas en los dos mareógrafos; en 2024 y antes los
  ficheros están casi completos. Una hora sin ningún minuto bueno se guarda como `missing`.
- Sustituye a los mareógrafos de SOCIB, que dejaron de publicar en Mallorca entre 2019 y 2024.

### Temperatura del mar por satélite (NOAA OISST)

La temperatura diaria de la superficie del mar de NOAA OISST v2.1 (satélite, barcos y boyas en una rejilla de 0,25°)
desde septiembre de 1981, en la celda de mar más cercana a cada uno de los 8 puntos de costa de Open-Meteo Marine.
Se lee del ERDDAP de NOAA CoastWatch sin clave: una caja de 3 × 5 celdas por ventana en lugar de una petición por
punto. El dato definitivo llega unos 16 días tarde y el provisional al día siguiente; son dos métricas, y gold toma
el definitivo en cuanto existe. Al eje de tiempo de ERDDAP le faltaban 1.196 días (casi todos de 1992-1998): el
conector los pide a la copia de NOAA PSL por OPeNDAP, y silver queda completo, 16.507 días en los 8 puntos.

En gold, `dim_sea_temperature_climatology` da la temperatura habitual de cada día del año en 1991-2020 (ventana de
11 días y media móvil de 31, como Hobday et al., 2016) y `fct_sea_temperature_daily` la anomalía y las **olas de
calor marinas**: 5 días seguidos o más por encima del percentil 90, con islas y huecos. La anomalía media pasa de
−0,48 °C en los ochenta a +1,05 °C desde 2020, y los días de ola de calor, de 1,5 al año a 136. La ola de 2026 frente
a Palma duró 131 días (del 15 de junio al 23 de octubre), con 29,9 °C el 7 de agosto, el valor más alto de la serie.
En la web, *Clima y agua* pone la anomalía del mar junto a la del aire; en Grafana hay además una tabla de olas de
calor. Open-Meteo Marine resulta entre 0,2 y 0,6 °C más cálido que el satélite, con r = 0,99.
[Detalle y pruebas reales](connectors/noaa_oisst/README.md).

### IGN (sismos)

Sismos localizados por el Instituto Geográfico Nacional, leídos del servicio FDSN de EMSC (estándar, sin clave)
en la caja de la región ampliada 1° alrededor de la isla. Es la primera fuente de **eventos**: no hay muestreo
regular, así que su dataset declara `frequency: event` (sin regla de huecos) y una ventana sin sismos, lo habitual,
es una ejecución correcta con 0 filas. En gold, `fct_earthquakes` da una fila por sismo con su distancia a Palma; en
Grafana aparecen en el mapa (tamaño y color según la magnitud) y en un indicador. Prueba real: 57 sismos desde 2020, magnitud máxima 3,0.

### EMT Palma (autobús)

El GTFS estático de EMT Palma (abierto en su GitHub, sin clave) convertido en una **serie diaria por parada**: para
cada día se resuelven los servicios que circulan (calendario semanal más las excepciones de festivos) y se cuentan
los autobuses programados y las líneas distintas que pasan por cada una de las 875 paradas. EMT publica los viajes
por frecuencias (`frequencies.txt`: «cada 20 min de 07:15 a 20:35»), que el conector expande. Los días fuera de la
vigencia del feed no generan filas, así que la regla de huecos los señala. En Grafana es un mapa de calor del
servicio. Prueba real: unos 78.000 pasos de autobús en un día laborable, 52.800 en domingo.

### CTM (autobús, tren y metro de la isla)

El GTFS del Consorci de Transports de Mallorca (sin clave, CC BY 4.0) con la misma lógica que EMT, ahora en
`core/connectors/gtfs.py`: autobuses TIB, tren SFM y metro programados y líneas por parada y día en las 763
paradas de la isla. Sin `frequencies.txt`, cada viaje cuenta una vez por parada; los horarios de temporada se ven
como servicios que acaban el 31 de octubre. En gold, `fct_island_transit_daily`; en Grafana, la misma mancha de
calor que EMT. Prueba real: unos 41.000 pasos en un día laborable, 35.000 en domingo; la Estació Intermodal de
Palma tiene 1.028 al día.

### BiciPalma (bici pública)

La primera **fuente en vivo**: el GBFS que Nextbike publica para BiciPalma (sin clave, CC0) solo da el estado de
ahora, sin histórico. Un DAG aparte, `live_poll`, guarda cada 5 minutos la respuesta tal cual en bronze, sin Spark
(unos 2 segundos y 75 MB por sondeo). El conector diario no llama a la API: lee esas instantáneas y escribe, por
estación y hora, la media, el mínimo y el máximo de las bicis y de los anclajes libres, las eléctricas y la
ocupación. Las horas anteriores al primer sondeo no cuentan como huecos
([ADR 0026](docs/adr/0026-fuentes-en-vivo-sin-historico.md)). CityBikes da los mismos números porque lee el mismo
feed, así que no sirve de respaldo. En gold, `fct_bike_stations_hourly` y `fct_bike_stations_daily`; en la web, las
106 estaciones en el mapa de Movilidad con su ficha. Prueba real: 581 bicis libres a media tarde, un 23 % eléctricas,
y entre 9 y 19 estaciones sin bicis en algún momento de cada hora.
[Detalle y pruebas reales](connectors/bicipalma/README.md).

### Calidad del aire (EEA)

Las medidas horarias de las 9 estaciones oficiales de Mallorca, desde el servicio de descarga de la Agencia Europea
de Medio Ambiente: una búsqueda JSON devuelve un Parquet por estación y contaminante, unas dos horas por detrás del
tiempo real. Se probaron antes OpenAQ y aqicn: republican las mismas estaciones, OpenAQ con solo un 30 % de las
horas y aqicn sin histórico y en subíndices AQI en lugar de concentraciones. Los
contaminantes se llaman como en Open-Meteo, y `fct_air_quality_model_bias_daily` compara cada estación con el modelo
CAMS. En Grafana, las estaciones aparecen en el mapa de Inicio y el error del modelo en Tiempo y entorno. Prueba
real: el modelo se queda corto de NO₂ junto al tráfico de Foners (−6 µg/m³) y se pasa de ozono en Palma (+20), que
es justo donde el NO del tráfico lo consume.

Los años anteriores salen de los ficheros verificados de la EEA (E1a, desde 2013), porque los *up-to-date* solo
traen el año en curso: el conector parte la ventana por años y busca cada parte en su conjunto. Un backfill de julio
de 2021 a 2025 (1,38 millones de valores horarios en 19 tramos, unos 10 minutos) une el histórico de la GOIB con los
datos actuales, y `fct_air_quality_monthly` queda continuo desde 2002. El NO₂ de Foners se queda en torno a 22 µg/m³
tras el confinamiento (21,6 en 2025), sin volver a los 31,6 de 2019.

### Histórico de calidad del aire (GOIB)

El catálogo de datos abiertos del Govern (API CKAN) tiene las medidas horarias de 11 estaciones de Mallorca de 2002 a
junio de 2021, y nada más reciente. Es un conector de histórico: desactivado en la ejecución diaria y cargado una vez
con `make backfill`. Los ficheros llegan en tres formatos distintos (separador, orden de la fecha y cabecera), y la
hora se comprobó hora a hora contra los ficheros verificados de la EEA. Las estaciones se llaman igual que en
`eea_air_quality`, y `fct_air_quality_monthly` las une en una serie mensual por estación. Prueba real: casi 5 millones de valores horarios en unos 45 minutos de backfill. El NO₂ de Foners, junto al tráfico de Palma, baja de 52,7 µg/m³ de media anual en 2002 (por encima del límite de la UE, 40) a 31,6 en 2019 y 24 en 2020, el año del confinamiento; el ozono de la isla sube de 56 a 70 µg/m³.

### Reservas hídricas

Las reservas de agua subterránea que publica cada mes el Govern: los últimos 13 meses de las 18 masas de agua de
Mallorca y de la isla en una hoja ODS, y diez años de la isla en el gráfico PDF, cuyas etiquetas son texto. Los
ficheros cambian de nombre cada mes, así que el conector los busca en la página por el texto del enlace. Como las
reservas son estacionales, `fct_water_reserves_monthly` compara cada mes con la media del mismo mes de otros años.
Prueba real: agosto de 2026, 38 %, el agosto más bajo de los diez años (11,5 puntos por debajo de la media).

### Aguas de baño (Náyade)

Cada muestra de las 87 aguas de baño de Mallorca (113 puntos de muestreo) de abril a septiembre: *E. coli*,
enterococos intestinales y el aviso que la acompaña, y las restricciones del baño. Náyade, el sistema nacional del
Ministerio de Sanidad, no tiene API: el conector lee sus páginas de formularios, que responden sin sesión, y guarda
las cuatro temporadas que enseña (desde 2023). Sin muestras en invierno, la fuente es de eventos: siete meses sin
datos no son huecos. En gold, `fct_bathing_water_seasons` calcula la clase de la directiva europea 2006/7/CE
(percentiles 95 y 90 de los logaritmos de cuatro temporadas) de cada agua de baño y temporada, con su cambio frente a
la anterior, y `fct_bathing_water_island_yearly` el porcentaje de excelentes: 73,6 % en 2024, 75,9 % en 2025 y
79,3 % en 2026 (69 excelentes, 16 buenas, 1 suficiente y 1 insuficiente). La web lo pinta en un mapa de Clima y
agua, con la ficha de cada playa, y Grafana en dos paneles. La clasificación oficial de la EEA queda pendiente: su
servicio no respondía el día de la prueba. [Detalle y pruebas reales](connectors/nayade/README.md).

### Dataestur (turismo)

Cuatro tablas mensuales de la API de SEGITTUR (sin clave): turistas internacionales (FRONTUR) y su gasto (EGATUR)
en Baleares, ocupación hotelera (EOH) y pasajeros del aeropuerto de Palma (AENA). La API responde xlsx, que el
conector lee con la librería estándar, y un filtro mal escrito devuelve una hoja vacía con HTTP 200, que se trata
como error. Es la primera fuente mensual: el núcleo gana `frequency: 1mo` (huecos contados en meses naturales) y
`min_days`, para que la ejecución diaria relea siempre el último año y recoja las revisiones. En gold,
`fct_tourism_monthly` con el gasto por turista y la variación interanual; en Grafana, un panel con los últimos tres
años. Prueba real: diez años en un minuto; agosto de 2026, 2,6 M turistas (+2,6 %) y 4,8 M pasajeros en Palma.

Los **cruceristas** salen de la misma API: el tráfico portuario de Puertos del Estado (`PUERTOS_DL`) para la
Autoritat Portuària de Balears, mensual desde 2005, con pasajeros de crucero, escalas y pasajeros totales. Es la
suma de sus cinco puertos (Palma es unos dos tercios), sin separar base y tránsito. La propia APB publica más
detalle, pero como una imagen PNG por puerto y mes; sus cifras coinciden con las de Dataestur. Son los pasajeros
que declara cada escala, no un recuento independiente (según la prensa, a menudo salen de la capacidad del barco).
Cada tabla empieza en un año distinto y `first_month` evita pedir meses que no existen (FRONTUR y EGATUR responden
HTTP 500 antes de 2016). En gold, los cruceristas, sus escalas y su variación interanual en
`fct_tourism_monthly`, y su anomalía frente al mismo mes en `fct_resources_monthly`; en la web y en Grafana, un
panel de cruceristas frente al aeropuerto. Prueba real: agosto de 2026, 393.270 cruceristas (+7,4 %) en 122 escalas.

Añadir una fuente: [docs/adding-a-connector.md](docs/adding-a-connector.md).

## Silver en Delta Lake

El lake de silver (`s3://silver/observations`) es una tabla [Delta Lake](https://delta.io/): ficheros Parquet con
una partición por fuente (`source=…`), más un `_delta_log` con un commit JSON por escritura que dice qué ficheros
forman cada versión ([core/lake.py](core/lake.py)).

- **`MERGE` en lugar de sobrescribir particiones.** Cada ejecución de un conector hace un `MERGE` por la clave
  (fuente, entidad, métrica, hora). Las filas nuevas se insertan, las que cambian se actualizan y las que no cambian
  se descartan antes, porque Delta reescribe todo fichero que tenga una fila coincidente. Así, relanzar una ventana
  sin cambios no escribe nada ni crea versión, igual que el upsert de Postgres no toca esas filas. La condición
  nombra la fuente y los días de la ventana, y las estadísticas de cada fichero (mínimo y máximo de `ts` y `date`)
  dejan fuera los que no tienen esos días.
- **Historial, *time travel* y cambios.** Cada commit es una versión. `make silver-history` las lista con sus filas
  insertadas y actualizadas, y la tabla se puede leer tal como estaba en una versión o una hora. `make silver-changes
  VERSION=n` lista las filas que aparecieron, desaparecieron o cambiaron de valor o de calidad desde la versión `n`.
  Lo hace con el *Change Data Feed*, que guarda las filas que tocó cada commit, en lugar de comparar dos copias de
  9 millones de filas: esa comparación se quedaba sin memoria con 1 GB.
- **Pocos ficheros grandes.** El lake Parquet tenía una partición por fuente y día: 16.973 particiones de unos
  17 KB, en 67.000 ficheros, cuando Delta y Athena trabajan mejor con ficheros de decenas de MB. La primera ejecución
  lo convierte en su sitio (`CONVERT TO DELTA`, que solo escribe el log) y lo reescribe una vez por fuente: quedan
  29 ficheros. `make silver-maintain` compacta cada fuente en ficheros de hasta 32 MB ordenados por hora
  (`OPTIMIZE … ZORDER BY (ts)`) y borra los que ya no forman parte de ninguna versión de los últimos 7 días
  (`VACUUM`). El *time travel* llega hasta donde llegan esos ficheros. Entre medias, la *auto compaction* de Delta
  junta el fichero nuevo de cada ejecución con los de su fuente: en el pipeline queda un fichero por fuente (8-25 s
  más por ejecución, dentro del *lock*).
- **Un escritor a la vez.** Delta en S3 no tiene un "escribir si no existe" atómico desde Spark, y el DAG ejecuta dos
  conectores a la vez, es decir, dos *drivers* de Spark. Un *advisory lock* de Postgres serializa los commits, en el
  papel que en AWS haría DynamoDB.
- **Sin paquete de Python.** `delta-spark` fija una versión de PySpark anterior a la del proyecto. La imagen trae
  solo los jars de Delta 4.4 para Spark 4.2, y el código usa SQL (`MERGE INTO`, `DESCRIBE HISTORY`,
  `readChangeFeed`).

Prueba real (2 de noviembre de 2026, 9,1 millones de filas):

| Paso | Resultado |
|---|---|
| Conversión del lake Parquet | 67.326 ficheros (288 MiB), 8 min, una sola vez |
| Reescritura por fuente | 16.960 ficheros → 29, 2,5 min, una sola vez |
| `OPTIMIZE … ZORDER BY (ts)` | 29 → 12 ficheros, 2,7 min (25 min con la partición por día, que dejaba 16.828) |
| Open-Meteo, 2 días nuevos | 4.320 filas insertadas, versión nueva |
| Relanzar la misma ventana | 0 filas, sin versión, 44 s |

En AWS, Athena lee la tabla con su log ([infra/terraform](infra/terraform/README.md)).

## Linaje con OpenLineage

Cada ejecución del DAG puede contar qué leyó y qué escribió cada paso, en el formato abierto
[OpenLineage](https://openlineage.io/). Los eventos los guarda y dibuja [Marquez](https://marquezproject.ai/), su
implementación de referencia. Es opcional: se activa con dos líneas del `.env` y, sin ellas, no se envía nada.

```bash
COMPOSE_PROFILES=lineage           # arranca Marquez: interfaz en http://localhost:3001, API en :5000
OPENLINEAGE_URL=http://marquez:5000
```

- **Airflow.** Las tareas declaran como *assets* los datos que leen y escriben, y el proveedor de OpenLineage los
  envía con cada ejecución:
  - `ingest` escribe bronze, la tabla Delta de silver y `silver.observations`;
  - `detect_anomalies` lee `silver.observations` y escribe `silver.anomalies`;
  - `correct_values` lee las dos y escribe `silver.corrections`.

  Los mismos *assets* aparecen en la vista *Assets* de Airflow.
- **dbt.** Con `OPENLINEAGE_URL`, `dbt_build` ejecuta `dbt-ol` en lugar de `dbt`. Cada modelo y cada test es un job
  con sus entradas, su salida y el **linaje por columna** (`gold.fct_observations.value` ← `stg_silver__observations.value`).
  Todos cuelgan de la ejecución de `dbt_build`.
- **Un solo grafo.** Las tablas tienen el mismo nombre en los dos lados (`postgres://postgres:5432`,
  `warehouse.silver.observations`). Así, el grafo une las tareas de Airflow con los modelos de dbt: de la ingesta a
  gold, pasando por anomalías y correcciones.

![Linaje de gold.fct_observations_corrected en Marquez](docs/img/linaje.png)

Prueba real (DAG con Open-Meteo y la EEA): 6 tareas de Airflow y 75 jobs de dbt en Marquez, y 12 columnas con linaje
en `gold.fct_observations`.

Spark no envía eventos propios. Sus filas salen de Python, no de una lectura de Spark, así que su integración solo
repetiría lo que ya declara `ingest`. Marquez no publica versión desde marzo de 2025 (0.51.1), pero los eventos son
OpenLineage estándar y cualquier otro *backend* los acepta cambiando `OPENLINEAGE_URL`.

## Calidad de datos

Reglas reutilizables en `core/quality/`, configuradas desde el YAML de cada conector:

| Regla | Tipo | Qué detecta |
|---|---|---|
| `not_null` | fila | valores nulos → `missing` |
| `source_qc` | fila | valores que la propia fuente marca como dudosos (p. ej. QC de SOCIB) → `suspect` |
| `range` | fila | valores fuera del rango físico de la métrica → `suspect` |
| `duplicate` | fila | misma (fuente, entidad, métrica, ts) repetida → se colapsa conservando el valor no nulo |
| `gaps` | serie | pasos de tiempo ausentes según la `frequency` del conector (no se aplica a fuentes de eventos) |

Resultados por ejecución en `quality.check_results`; en Grafana, el % de sospechosos, la completitud de la tabla de
series y la fila plegada *Operación*.

## Detección de anomalías

Las reglas de calidad descartan lo imposible (una humedad del 140 %); los detectores de `core/anomaly/` buscan lo
improbable: valores posibles que no encajan con su propia serie. Solo **marcan**: escriben en `silver.anomalies`
(valor, valor esperado, puntuación, umbral, `run_id`) y nunca modifican `silver.observations`.

- **Interfaz `Detector`**: puntúa todas las series de una entidad (localidad, estación o punto) en pandas, así se
  prueba sin Spark; el runner la reparte por entidades con `groupBy().applyInPandas()`. Los detectores univariantes
  (`UnivariateDetector`) miran cada métrica por separado; los multivariantes, cómo se mueven juntas.
- **`robust_zscore`**: z-score modificado de Iglewicz y Hoaglin, `0,6745 · (x − mediana) / MAD` sobre una ventana
  móvil centrada (7 días en series horarias, 31 en diarias). La mediana y la MAD apenas se mueven con el pico que
  buscan, al contrario que la media y la desviación típica. Una ventana casi constante (MAD = 0) no se puntúa.
- **`seasonal_residual`**: quita el ciclo antes de puntuar. El valor esperado es la mediana de la misma hora en los
  3 días anteriores y los 3 siguientes (el mismo día de la semana en las series diarias), y el residuo se puntúa
  como el z-score. También puntúa el **cambio** desde la hora anterior frente al de esa hora otros días: el tiempo
  de un día mueve el nivel de todas las horas, pero mucho menos cuánto se calienta o se enfría cada una. Un cambio
  raro implica dos valores y se culpa al más alejado de su nivel, así que la vuelta a la normalidad tras un fallo
  marca el último valor malo y no el primero bueno. Es el único que ve un reloj desfasado.
- **`isolation_forest`** (scikit-learn): un bosque por entidad sobre todas sus métricas a la vez. Cada instante se
  describe, por métrica, con su valor, su cambio, cuántos valores seguidos lleva igual y la distancia al valor
  habitual a esa hora, más la propia hora. Aísla los instantes raros (un 5 % de cada entidad, `contamination`) y
  culpa a la métrica cuyas variables más se alejan de su mediana. Necesita 48 instantes completos: las series
  diarias de AEMET no llegan.
- **`vote`**: la respuesta de la plataforma. Une el residuo estacional y el bosque, que fallan en cosas distintas
  (`min_votes: 1`; con 2 solo queda lo que marcan los dos). Su puntuación es el número de votos.
- Tarea `detect_anomalies` del DAG tras la ingesta, también si alguna fuente falló. Cada ejecución vuelve a puntuar
  al menos los últimos `rescore_days` (14) y reemplaza su resultado: los datos que llegan tarde (AEMET) o se
  recuperan se juzgan con sus vecinos, y es idempotente.
- Configuración en [config/anomaly.yaml](config/anomaly.yaml): parámetros de cada detector y lo que no se analiza
  (sismos, horarios de EMT y CTM y estadísticas mensuales de Dataestur y de reservas hídricas; precipitación, insolación y dirección del
  oleaje). A mano: `make detect DAYS=30`.

Con 30 días reales (195 000 valores) el z-score marca 1 738, sobre todo episodios de verdad (el temporal del 18-19
de octubre, mar de fondo en Alcúdia) y los picos nocturnos de NO₂; el residuo estacional, 1 644; el Isolation
Forest, 1 112, y la votación, 2 404 (un 1,2 %). Los cuatro tardan 2 min 50 s en Spark local.

En Grafana, las anomalías se dibujan como anotaciones sobre las series: en el explorador de Tiempo y entorno (la
métrica y las entidades elegidas), en el NO₂ de las estaciones (desactivada por defecto, porque son nueve) y en el
antes y después de Operación. Las horas anómalas seguidas de una serie son una sola banda, con el rango de valores y
el valor esperado, así que un temporal es una marca y no treinta. Las tablas de Operación las listan una a una.

### Medir los detectores con fallos inyectados

Las anomalías reales no vienen etiquetadas, así que no se puede saber cuántas se escapan. `make evaluate` crea esa
verdad: toma las series recientes de tres fuentes, les **inyecta fallos conocidos** con una semilla fija y puntúa cada
serie limpia y corrompida (`core/anomaly/faults.py` y `evaluation.py`). Cada fuente se mide por separado, porque no
son igual de fáciles:

- **Open-Meteo**: un modelo, con series completas y suaves. Es el caso fácil.
- **SOCIB**: estaciones meteorológicas reales, con el ruido de sus sensores.
- **EEA**: estaciones de calidad del aire, con contaminantes que suben y bajan con el tráfico.

| Fallo | Qué simula | Forma | Alcance |
|---|---|---|---|
| `spike` | lectura errónea, coma decimal | un valor ± 4-8 σ robustas | una serie |
| `frozen` | payload repetido, registrador colgado | 6-24 horas con el último valor bueno | toda la estación |
| `drift` | sensor que se descalibra | rampa de 2-4 σ durante 48-120 horas | una serie |
| `shift` | reloj o zona horaria mal | 6-24 horas con los valores de 12 horas antes | toda la estación |

Un reloj mal o un payload repetido no afectan a un solo sensor: el registrador es el mismo para toda la estación. Por
eso `frozen` y `shift` caen a la vez, y en las mismas horas, en todas sus métricas (`scope: station` en
`config/anomaly.yaml`).

Un aviso sobre un valor inyectado es un acierto; uno nuevo sobre un valor limpio, una falsa alarma. Lo que el
detector ya marcaba en la serie limpia (episodios reales) se cuenta aparte y no penaliza. Los huecos no se inyectan:
un valor que falta no se puede marcar, y ya los cuenta la regla `gaps`. Resultados en
`quality.anomaly_evaluations`; fallos detectados (algún valor marcado) en los 30 días hasta el 22 de noviembre de
2026, con 39.720 valores de Open-Meteo, 13.332 de SOCIB y 21.859 de la EEA:

| Fuente | Detector | Picos | Derivas | Congelados | Desfase | Precisión |
|---|---|---|---|---|---|---|
| Open-Meteo | `robust_zscore` | 88 % | 11 % | 0 % | 6 % | 87 % |
| Open-Meteo | `seasonal_residual` | 97 % | 83 % | 24 % | 50 % | 81 % |
| Open-Meteo | `isolation_forest` | 24 % | 11 % | 24 % | 0 % | 87 % |
| Open-Meteo | `vote` (estacional o bosque) | 98 % | 83 % | 44 % | 50 % | 83 % |
| SOCIB | `robust_zscore` | 86 % | 29 % | 0 % | 4 % | 70 % |
| SOCIB | `seasonal_residual` | 96 % | 75 % | 17 % | 29 % | 65 % |
| SOCIB | `isolation_forest` | 33 % | 8 % | 33 % | 0 % | 89 % |
| SOCIB | `vote` | 96 % | 75 % | 42 % | 29 % | 74 % |
| EEA | `robust_zscore` | 88 % | 44 % | 3 % | 19 % | 76 % |
| EEA | `seasonal_residual` | 95 % | 69 % | 11 % | 33 % | 62 % |
| EEA | `isolation_forest` | 49 % | 25 % | 42 % | 11 % | 86 % |
| EEA | `vote` | 97 % | 72 % | 44 % | 36 % | 69 % |

El z-score ve lo que se aleja de sus vecinos y es ciego a lo que se queda en un nivel normal: un sensor congelado en
18 °C está cerca de la mediana, y en un modelo suave los valores de 12 horas antes parecen una noche templada. El
bosque ve que una serie que siempre se mueve se ha parado (con la variable "valores seguidos iguales"; una
dispersión móvil no basta, porque cerca del máximo o el mínimo diario casi no hay dispersión de todos modos), pero
con su cupo del 5 % se deja la mitad o más de los picos. El residuo estacional ve el desfase porque compara cada hora
con la misma hora de otros días, y sobre todo porque compara el cambio: con el reloj mal, la serie se enfría cuando
debería calentarse. Ojo con sus derivas: casi siempre las ve donde acaban, en el salto de vuelta, no mientras crecen.

**Lo que cambia con estaciones reales.**

- **La precisión baja.** El residuo y la votación pasan del 81-83 % en el modelo al 62-74 % en las estaciones: el
  ruido real y los episodios cortos, como un pico de NO₂ en hora punta, se parecen más a un fallo. El bosque es el que
  mejor la conserva (86-89 %), porque solo marca su cupo.
- **El desfase de reloj es el fallo más difícil fuera del modelo.** El residuo pasa del 50 % al 29-33 %: la curva
  diaria de una estación es menos regular que la de un modelo, así que doce horas corridas destacan menos.
- **Los congelados de toda la estación los ve sobre todo el bosque** (24-42 %), que mira todas las métricas juntas.
  La votación llega al 42-44 % en las tres fuentes.
- **En calidad del aire, el z-score ve más derivas** (44 %) que en el tiempo: los contaminantes no tienen un ciclo
  diario tan marcado, así que una rampa se sale antes de lo normal.

La votación une los dos que fallan en cosas distintas: suma los congelados del bosque a lo que ve el residuo y, en las
estaciones, recupera parte de la precisión que pierde el residuo solo. Con Open-Meteo, antes de medir las estaciones,
añadir el z-score solo le quitaba precisión (74 %) sin ganar fallos, y exigir dos votos subía la precisión al 86 % a
cambio de dejarse la mitad. `contamination` mueve el equilibrio del bosque: con 0,10 llega a más picos y congelados
con algo menos de precisión.

## Correcciones con fuentes de apoyo

Las estaciones horarias (SOCIB y la EEA) tienen huecos: cortes de la fuente, horas que la red marca como no
válidas y valores sospechosos que fallan una regla de calidad. `core/corrections/` **propone** un valor para esas
horas y lo guarda aparte, en `silver.corrections`, con el valor original, el método, la serie de apoyo, su sesgo y
una confianza de 0 a 1. `silver.observations` nunca cambia: `gold.fct_observations_corrected` pone los dos valores
lado a lado, y `value` es el corregido donde lo hay y el original en el resto.

- **Qué se corrige**: cada hora sin valor válido entre dos valores de la estación: falta, es sospechosa o no tiene
  fila. Los valores que marcan los detectores de anomalías no se tocan, porque uno de cada cinco es un episodio real
  y corregirlo lo borraría.
- **Método 1, interpolación**: los huecos de hasta 3 horas se rellenan interpolando en el tiempo entre los valores de
  la propia estación. Confianza `exp(−horas / 6)`: 0,85 con una hora, 0,61 con tres.
- **Método 2, fuente de apoyo**: en los huecos más largos, la serie de la misma métrica mejor correlacionada a menos
  de 30 km, que puede ser otra estación de la misma red o el punto del modelo de Open-Meteo. Hacen falta una semana
  de horas en común y una r ≥ 0,6. El valor de apoyo se desplaza con su sesgo, la mediana de "estación menos apoyo",
  calibrado **por hora del día** con los 30 días anteriores. Así recoge la brisa, la altitud y el ciclo diario del
  modelo. Confianza `r² · exp(−distancia / 100 km) · exp(−horas / 7 días)`.
  - **PM10 y PM2.5 se prueban en lugar de exigir la r** (`support.backtest`). El modelo CAMS sigue sus días de
    polvo, viento o lluvia, pero no su ruido hora a hora, así que su r se queda entre 0,2 y 0,6. Cuando ningún apoyo
    llega a 0,6, se cortan huecos de 24 horas en el histórico de la propia estación y se rellenan con cada apoyo y con
    una recta. Gana el apoyo que menos se equivoca, y solo si se equivoca menos que la recta en al menos 7 huecos.
  - Ese apoyo solo rellena huecos de 12 horas o más: en los de 6 horas, una recta se equivoca menos que el modelo.
- **Método 3, perfil semanal**: el NO₂ y el CO vienen del tráfico de cada calle y casi nunca tienen un apoyo con
  r ≥ 0,6. Para sus huecos largos sin apoyo se usa el ciclo de la propia estación: la mediana de cada hora local de
  los días laborables y de los fines de semana en los 30 días anteriores, desplazada al nivel de los valores a cada
  lado del hueco (la diferencia con el perfil se interpola a través del hueco). La hora es la de la isla, con el
  horario de verano, porque el tráfico sigue al reloj. Confianza `r² · exp(−horas / 2 días)`, con la r de la
  estación frente a su perfil. Solo para las métricas en las que el benchmark lo respalda (`profile.metrics`).
- Tarea `correct_values` del DAG tras la detección. Cada ejecución recalcula los últimos 14 días: una corrección
  desaparece cuando llega el valor real, y es idempotente. Configuración en
  [config/corrections.yaml](config/corrections.yaml); a mano, `make correct DAYS=30`.

`make evaluate-corrections` mide las correcciones con una verdad conocida. Esconde valores limpios de las
estaciones en huecos de 1, 3, 6 y 24 horas, los corrige y compara. Resultado de 14 días reales, con el error medio
absoluto (MAE) y, para la fuente de apoyo, el que tendría sin su sesgo:

| Serie | 1 h | 3 h | 24 h (apoyo) | 24 h sin sesgo |
|---|---|---|---|---|
| Temperatura (SOCIB) | 0,26 °C | 0,41 °C | 1,35 °C | 2,19 °C |
| Presión (SOCIB) | 0,11 hPa | 0,23 hPa | 0,20 hPa | 14,0 hPa |
| Humedad (SOCIB) | 1,8 % | 2,7 % | 7,6 % | 9,6 % |
| Ozono (EEA) | 3,6 µg/m³ | 6,0 µg/m³ | 7,4 µg/m³ | 13,2 µg/m³ |
| NO₂ (EEA) | 1,6 µg/m³ | 2,0 µg/m³ | 1,1 µg/m³ (solo 140 de 456 h) | 2,3 µg/m³ |

- **La presión** muestra para qué sirve el sesgo. La de Parc Bit es unos 14 hPa más baja que la de la boya de la
  bahía, que es la que más se le parece (r = 1,00). Parece presión a la altura de la estación, sin reducir al nivel
  del mar: unos 115 m. Sin el sesgo, el apoyo se equivocaría en 14 hPa; con él, en 0,2.
- **El NO₂** es muy local: viene del tráfico de cada calle y casi ninguna estación tiene un apoyo con r ≥ 0,6. Solo
  S'Albufera y Sa Pobla se apoyan la una en la otra. El perfil semanal cubre el resto: en huecos de 24 horas
  corrige 532 de las 720 horas escondidas que antes se quedaban sin valor, con un error de 3,3 µg/m³ frente a los
  4,7 de una recta entre los dos lados del hueco. Una recta se salta las horas punta; el perfil sabe cuándo son.
  MAE de las horas que corrige el perfil, 14 días hasta el 14 de noviembre de 2026:

  | Serie | 6 h, perfil | 6 h, recta | 24 h, perfil | 24 h, recta |
  |---|---|---|---|---|
  | NO₂ (EEA) | 3,3 µg/m³ | 4,3 µg/m³ | 3,3 µg/m³ | 4,7 µg/m³ |
  | CO (EEA) | 74 µg/m³ | 86 µg/m³ | 77 µg/m³ | 168 µg/m³ |

- **PM10, PM2.5, ozono y las variables del tiempo** no usan el perfil: el benchmark da con él el mismo error que con
  una recta, o más, porque los mueve el tiempo y no el reloj.
- **En PM10 y PM2.5, el modelo CAMS sí sirve aunque su r no llegue a 0,6**. Con la prueba sobre el histórico de cada
  estación, en 28 días hasta el 22 de noviembre de 2026 (6 huecos escondidos por serie y longitud):
  - PM10 corrige 765 de las 960 horas escondidas en huecos de 24 horas, en lugar de 279.
  - PM2.5, que no tenía ningún apoyo, corrige 208 de 240.
  - El error medio absoluto queda entre un 8 % y un 41 % por debajo del de una recta:

  | Serie | Horas corregidas, antes | Horas corregidas, ahora | MAE, apoyo | MAE, recta |
  |---|---|---|---|---|
  | PM10, huecos de 12 h | 144 de 504 | 426 de 504 | 4,3 µg/m³ | 4,7 µg/m³ |
  | PM10, huecos de 24 h | 279 de 960 | 765 de 960 | 3,8 µg/m³ | 6,4 µg/m³ |
  | PM2.5, huecos de 12 h | 0 de 144 | 120 de 144 | 2,7 µg/m³ | 3,9 µg/m³ |
  | PM2.5, huecos de 24 h | 0 de 240 | 208 de 240 | 3,9 µg/m³ | 5,6 µg/m³ |

  La confianza sigue la misma fórmula, con `r²` por debajo de 0,36, así que es baja: el valor es mejor que una
  recta, pero no se parece a la estación hora a hora. Las horas que no se corrigen son de estaciones donde ningún
  apoyo pasa la prueba.
  `make evaluate-corrections` muestra ahora también la recta de las horas del apoyo (columna `line`).
- **Las rachas de viento** son el único caso en el que el sesgo no ayuda: 7,5 frente a 6,8 km/h en huecos de 6
  horas. Una racha es un máximo puntual y no guarda una diferencia estable con otra estación.

En Grafana, el tablero Operación muestra las correcciones por día y método, una gráfica de antes y después de la
serie elegida (variable *Serie corregida*) y la tabla de las últimas correcciones. Las anomalías de esa serie aparecen
como bandas sobre la gráfica, igual que en el explorador de Tiempo y entorno: así se ve qué corrige cada parte. La
API las sirve en `GET /v1/corrections`.

## Frontal web

La isla en cifras, para quien quiere verla y no operar la plataforma: http://localhost:3002. Un menú a la izquierda
abre seis dashboards y un explorador de series. Cada dashboard agrupa datos que van juntos, igual que las carpetas de
Grafana. Está en castellano, catalán e inglés: el idioma va en la dirección (`/ca/movilidad`) y se cambia en el menú
([ADR 0024](docs/adr/0024-la-web-en-tres-idiomas.md)).

| Dashboard | Qué enseña |
|---|---|
| **Inicio** | Cinco cifras clave frente a lo normal de cada mes (reservas, lluvia, turistas, electricidad y temperatura) y el mapa de estaciones y puntos de modelo |
| **Turismo y recursos** | Turistas, aeropuerto y ocupación hotelera; turistas frente a reservas de agua y a demanda eléctrica, y ocupación frente a gasto, cada serie con su tendencia de 12 meses y su correlación de Pearson (con y sin el ciclo anual) |
| **Clima y agua** | Reservas frente a la media del mes, los 18 acuíferos, lluvia acumulada de cada año hidrológico y anomalía de temperatura |
| **Movilidad** | Población de la isla y servicio por cada 1.000 habitantes; mapa de los municipios por densidad, servicio por habitante o crecimiento en 10 años; población desde 1996; servicio programado de EMT y CTM por día, mapa del servicio de cada parada y paradas con más servicio; mapa de las líneas de autobús, tren y metro con su recorrido y sus salidas; estaciones de BiciPalma en el mapa (con su ficha al pulsarlas), la red hora a hora y las estaciones que más se vacían |
| **Tiempo y entorno** | Temperatura por zonas (las 33 estaciones de AEMET interpoladas sobre la isla), avisos de AEMET por zona (ahora y en las próximas 72 h), temperatura de cada fuente, calidad del aire ahora (índice europeo) con la tabla de estaciones, oleaje, episodios, sismos y error del modelo |
| **Explorador** | Cualquier serie de la plataforma día a día (fuente, métrica y entidad): media, mínimo y máximo, completitud, valores sospechosos y días con anomalías; la selección queda en la dirección para compartirla |
| **Operación** | Estado de cada fuente frente a su SLA, gobierno del dato (dueño, licencia y acceso), reglas de calidad que fallan, anomalías por día y últimas correcciones |

En cada cifra, la desviación sale en verde o en rojo cuando es buena o mala noticia, junto con la evolución de los
últimos meses. Los mapas tienen capas que se pueden ocultar, y al pulsar un punto se ve qué es.

| Turismo y recursos | Clima y agua |
|---|---|
| [![Turismo y recursos](docs/img/web/turismo-y-recursos.png)](docs/img/web/turismo-y-recursos.png) | [![Clima y agua](docs/img/web/clima-y-agua.png)](docs/img/web/clima-y-agua.png) |
| **Movilidad** | **Tiempo y entorno** |
| [![Movilidad](docs/img/web/movilidad.png)](docs/img/web/movilidad.png) | [![Tiempo y entorno](docs/img/web/tiempo-y-entorno.png)](docs/img/web/tiempo-y-entorno.png) |
| **Explorador** | **Operación** |
| [![Explorador](docs/img/web/explorador.png)](docs/img/web/explorador.png) | [![Operación](docs/img/web/operacion.png)](docs/img/web/operacion.png) |
| **Modo oscuro** | **En catalán** |
| [![Inicio en modo oscuro](docs/img/web/inicio-oscuro.png)](docs/img/web/inicio-oscuro.png) | [![Inicio en catalán](docs/img/web/inicio-catalan.png)](docs/img/web/inicio-catalan.png) |

Está hecha con React, TypeScript y Vite, con ECharts para los gráficos y MapLibre con teselas de OpenStreetMap para
los mapas. El logo es la silueta de la isla. Tiene modo claro y oscuro, con un botón en el menú que se recuerda en el
navegador, y en el móvil el menú pasa a ser un cajón.

**Solo lee la API REST**, nunca el warehouse. La imagen `web` es nginx con la web ya construida, y hace de proxy de
`/api` hacia la API, así que el navegador habla con un único origen. Grafana se queda para operar la plataforma:
alertas, calidad, anomalías y correcciones. Por qué una web propia y no rehacer Grafana:
[ADR 0019](docs/adr/0019-frontal-web-sobre-la-api.md).

Sus tipos salen del OpenAPI de la API (`web/src/api.gen.ts`, generado con `make web-types`), y un test falla si el
fichero no coincide con lo que sirve la API. Un campo que cambia en `api/schemas.py` aparece así en el `tsc` de la web
y no en una página rota.

```bash
cd web && npm install && npm run dev   # http://localhost:5173, con /api hacia la API del stack (localhost:8000)
npm test                               # cifras, estado de las fuentes y páginas (Vitest, Testing Library)
```

## Grafana

Seis dashboards en la carpeta *Mallorca Data Platform* (http://localhost:3000), enlazados entre sí desde la barra
superior. Cada uno responde a una pregunta y lee sus marts de dbt (un exposure por dashboard):

| Dashboard | Qué muestra |
|---|---|
| **Inicio** | El último mes de reservas hídricas, lluvia del año hidrológico, temperatura y turistas, y el mapa de todas las fuentes georreferenciadas (aire, oleaje, AEMET, SOCIB, sismos y servicio de bus) |
| **Turismo y recursos** | Turistas frente a reservas de agua y demanda eléctrica; las anomalías frente al mismo mes, que quitan la estacionalidad; y una evaluación año a año (turistas de verano frente a la caída de las reservas de marzo a septiembre, con su correlación) |
| **Clima y agua** | Reservas frente a la media del mes, lluvia mensual y respuesta de los acuíferos, tabla por año hidrológico, anomalía de temperatura, lluvia acumulada y el estado de los 18 acuíferos |
| **Movilidad** | Servicio programado de EMT Palma y CTM por día, mapa de calor por parada y paradas con más servicio; BiciPalma hora a hora |
| **Tiempo y entorno** | Explorador de cualquier métrica por fuente y entidad, con sus anomalías como anotaciones, calidad del aire, oleaje, error del modelo frente a las estaciones, episodios meteorológicos y sismos |
| **Operación** | Salud de cada fuente, anomalías detectadas, correcciones (antes y después), ejecuciones, reglas de calidad y completitud de cada serie |

| Inicio | Turismo y recursos |
|---|---|
| [![Inicio](docs/img/grafana/inicio.png)](docs/img/grafana/inicio.png) | [![Turismo y recursos](docs/img/grafana/turismo-y-recursos.png)](docs/img/grafana/turismo-y-recursos.png) |
| **Clima y agua** | **Movilidad** |
| [![Clima y agua](docs/img/grafana/clima-y-agua.png)](docs/img/grafana/clima-y-agua.png) | [![Movilidad](docs/img/grafana/movilidad.png)](docs/img/grafana/movilidad.png) |
| **Tiempo y entorno** | **Operación** |
| [![Tiempo y entorno](docs/img/grafana/tiempo-y-entorno.png)](docs/img/grafana/tiempo-y-entorno.png) | [![Operación](docs/img/grafana/operacion.png)](docs/img/grafana/operacion.png) |

Las capturas de la web y de Grafana se regeneran con `make screenshots` (Playwright en Docker contra la pila local).

La pregunta de fondo (¿aprieta el turismo al agua?) necesita cuidado: turismo, calor, demanda y reservas son
estacionales a la vez, así que comparar meses tal cual solo enseña el calendario. Los paneles de evaluación comparan
cada mes con la media del mismo mes y cada verano con los demás veranos. Con diez años de datos (correlaciones de
Pearson, pocos años, así que orientativas):

- La lluvia de septiembre a febrero explica bien las reservas de marzo (r = 0,78 en 10 años).
- Los veranos con más turistas son los que más bajan los acuíferos de marzo a septiembre (r = 0,50 en 9 años); la
  lluvia del año apenas cambia esa caída (r = 0,20).
- Mes a mes, los meses con más turistas de lo normal tienen reservas por debajo de lo normal (r = −0,41), pero en la
  década crece el turismo y bajan las reservas, y 2020 (sin turistas y con un invierno lluvioso) pesa mucho:
  correlación, no causa.

### Alertas

Cuatro reglas de alerta provisionadas desde `dashboards/provisioning/alerting/alerting.yml`. Se evalúan cada 5
minutos y cada fuente (o regla) es una alerta aparte. Tres leen solo las tablas operativas (`ops.ingestion_runs`,
`quality.check_results`), así que avisan aunque dbt no corra. La del SLA lee además el catálogo de fuentes y
`gold.source_health`:

| Alerta | Cuándo salta |
|---|---|
| **Ingesta fallida** | La última ejecución de una fuente terminó en `failed` |
| **Fuente sin ejecución correcta** | Una fuente activa (con datos del último año) lleva más de 36 h sin una ejecución correcta. Un backfill de histórico no cuenta |
| **Fuente fuera de su SLA** | Una fuente activa no cumple el SLA de su ficha: su último dato es más antiguo de lo acordado o tiene menos cargas correctas en 7 días de las acordadas ([gobierno del dato](docs/data-governance.md)) |
| **Regla de calidad en rojo** | Una regla pasó en el chequeo anterior y falla en el último. Las que fallan siempre (los huecos de una fuente con cortes conocidos) no avisan |

Las alertas activas aparecen en el panel *Alertas* de Operación. Para recibirlas en **Telegram**, opcional:

1. Crea un bot con [@BotFather](https://t.me/BotFather) y guarda su token.
2. Escríbele cualquier mensaje y lee tu chat id en `https://api.telegram.org/bot<token>/getUpdates`
   (`message.chat.id`).
3. Pon `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en el `.env` y reinicia Grafana (`docker compose up -d grafana`).

El entrypoint de Grafana (`docker/grafana/entrypoint.sh`) provisiona el punto de contacto y la política solo cuando
las dos variables existen, y los borra si se quitan. Sin ellas todo funciona igual, por ejemplo en el E2E. Llega
un mensaje por regla y fuente cuando salta una alerta, otro cuando se resuelve, y se repite cada 12 h mientras siga
activa.

Los nombres de las fuentes salen del seed `dim_sources` de dbt, que es también su ficha de gobierno (dueño, licencia,
acceso y SLA). Un test comprueba que toda fuente de silver tiene su fila.

## API REST

Una API de solo lectura con FastAPI sobre la capa gold, en su propio servicio (`api`, puerto 8000) y con su propia
imagen, pequeña: sin Airflow, Spark ni Java. La documentación OpenAPI está en http://localhost:8000/docs (Swagger) y
`/redoc`.

| Endpoint | Qué devuelve |
|---|---|
| `GET /v1/health` | Estado de la API y de su conexión al warehouse (503 si está caído) |
| `GET /v1/sources`, `/v1/sources/{source}` | Cada fuente con su última ejecución, % de fallos en 7 días, antigüedad del último dato, su ficha de gobierno (dueño, licencia, acceso, datos personales) y su SLA con si se cumple |
| `GET /v1/locations` | Cada estación, punto de modelo y parada con coordenadas, su fuente y su tipo (el mapa de la web) |
| `GET /v1/mobility/daily`, `/v1/mobility/stops`, `/v1/mobility/routes` | Servicio programado de EMT y CTM por día, el de cada parada en el último día y cada línea con su recorrido (GeoJSON) y sus salidas |
| `GET /v1/mobility/bike-stations`, `/v1/mobility/bikes/hourly` | Cada estación de BiciPalma en el último día (bicis, ocupación, horas sin bicis o llena) y toda la red hora a hora |
| `GET /v1/weather/daily`, `/v1/weather/stations`, `/v1/weather/episodes`, `/v1/weather/model-bias` | Tiempo diario de cada fuente, episodios de lluvia, viento o mar, y error del modelo frente a cada estación; `stations`: cada estación en el último día publicado |
| `GET /v1/air-quality/latest`, `/v1/sea/hourly`, `/v1/earthquakes` | Última hora de calidad del aire con su índice europeo, oleaje por hora y sismos |
| `GET /v1/sea/model-bias` | Error del modelo de oleaje frente a cada boya de SOCIB: sesgo, error medio, RMSE y correlación de la altura significativa hora a hora |
| `GET /v1/warnings`, `/v1/warnings/zones` | Avisos de AEMET en vigor o anunciados (por defecto, de ahora a 3 días) y las zonas de aviso con su polígono |
| `GET /v1/population`, `/v1/municipalities` | Población de cada municipio por año (filtrable con `from` y `to`) y los 53 municipios con su superficie y su límite |
| `GET /v1/quality/rules`, `/v1/anomalies/daily` | Último chequeo de cada regla de calidad y anomalías por día y detector |
| `GET /v1/anomalies/benchmark` | El último benchmark de cada fuente: fallos inyectados que detecta cada detector, y su precisión |
| `GET /v1/series`, `/v1/series/daily` | Las series diarias de una fuente (entidad con su nombre, métrica, unidad y días que cubre) y una serie día a día: mínimo, media, máximo, completitud, sospechosos y anomalías (por defecto, un año) |
| `GET /v1/observations` | Valores de una fuente filtrados por métrica, entidad y rango de tiempo (por defecto, los últimos 7 días), paginados |
| `GET /v1/observations/export` | Los mismos valores como fichero, sin paginar: CSV (`format=csv`, en streaming) o Parquet (`format=parquet`, zstd, `ts` en UTC); hasta 366 días y un millón de valores |
| `GET /v1/anomalies` | Valores marcados por los detectores, filtrados por fuente, detector y rango, paginados |
| `GET /v1/corrections` | Valores propuestos para las horas sin valor válido de las estaciones, con el original, el método, el apoyo, el sesgo y la confianza; filtrados por fuente, estación, método y rango, paginados |
| `GET /v1/water/reserves`, `/v1/water/aquifers` | Reservas mensuales con su anomalía y los 18 acuíferos del último mes |
| `GET /v1/climate/monthly`, `/v1/tourism/monthly`, `/v1/resources/monthly` | Los marts mensuales de los dashboards, filtrables con `from` y `to` |

```bash
curl "http://localhost:8000/v1/observations?source=aemet&metric=temperature_2m_max&entity=B278&limit=2"
```

```bash
curl -OJ "http://localhost:8000/v1/observations/export?source=socib&start=2026-01-01T00:00:00Z&format=parquet"
```

Decisiones:

- **Solo marts con contrato**: la API lee tablas de dbt con `contract: {enforced: true}`, así que sus columnas y tipos
  no cambian sin que falle el build. En CI, los tests de integración ejecutan cada consulta contra los marts recién
  construidos.
- **Rol propio de solo lectura** (`api_reader`, `docker/postgres/init/02-api-reader.sh`): `SELECT` sobre gold y silver,
  transacciones de solo lectura y un límite de 15 s por consulta. En un volumen ya creado: `make api-role`.
- **Paginación** con `limit` (como mucho 1000) y `offset`: la respuesta trae `next_offset`, que se calcula pidiendo una
  fila de más. **Errores** con una sola forma: `{"error": {"code": "not_found", "message": "..."}}`.
- **Caché de los marts diarios y límite por cliente** ([ADR 0023](docs/adr/0023-cache-y-limite-en-el-proceso-de-la-api.md)):
  las respuestas de reservas, clima, turismo, recursos, población y municipios se guardan una hora en memoria
  (`X-Cache: HIT`), con un `ETag` que devuelve 304 sin cuerpo. Cada cliente tiene 300 peticiones por minuto
  (cabeceras `RateLimit-*`; 429 con `Retry-After` por encima). Los dos viven en cada worker, sin Redis:
  `API_CACHE_SECONDS` y `API_RATE_LIMIT_PER_MINUTE` (0 los apaga).
- **Exportación por lotes**: el CSV sale de un cursor del servidor de Postgres, de 10 000 en 10 000 filas, mientras
  se escribe la respuesta; el Parquet se escribe en grupos de filas de 50 000. La memoria no crece con el tamaño del
  fichero. El explorador de la web enlaza los dos para la serie y el periodo elegidos.
- **Capa de acceso a datos sustituible** (`api/repository.py` sobre un protocolo `Database`): los tests unitarios usan una
  base de datos falsa y no necesitan Postgres. `make api-test`.

## AWS con Terraform

`infra/terraform` describe la misma plataforma en AWS:
- S3 para bronze y silver;
- Glue Data Catalog y Athena para consultar silver con SQL sin servidor;
- dos roles de IAM de mínimo privilegio;
- un presupuesto de 2 USD al mes.

No se despliega. El CI lo valida y lo prueba con `terraform test` contra un proveedor de AWS simulado, sin cuenta
ni coste (`make tf-check` en local). El diagrama local frente a AWS, los costes y lo que faltaría para correr en
AWS de punta a punta están en [infra/terraform/README.md](infra/terraform/README.md).

## Databricks

`databricks/` es la misma plataforma en un espacio de trabajo de Databricks Free Edition: un Lakeflow Job,
descrito como bundle, que corre en cómputo serverless y guarda cada capa en Unity Catalog. La pila local no cambia.

- **Extracción:** Open-Meteo y la EEA, con los mismos conectores que Airflow, a un Volume con las claves de MinIO.
- **Bronze:** Auto Loader.
- **Silver:** el `normalize()` y las reglas de calidad del núcleo, y un `MERGE` en la clave.
- **Gold:** cuatro tablas diarias en Databricks SQL, entre ellas el sesgo del modelo CAMS frente a las estaciones.
- **Permisos:** un esquema por capa, y lectura solo sobre gold para `account users`.

```bash
cd databricks
databricks bundle deploy -p mallorca
databricks bundle run mallorca_pipeline -p mallorca
```

Una ejecución tarda unos 2 minutos. Con la ventana de 3 días carga 6.912 filas en silver, y al relanzarla no
inserta ni actualiza ninguna. Cómo se instala la CLI, la comparación con la pila local y los resultados están en
[databricks/README.md](databricks/README.md). La decisión está en la
[ADR 0025](docs/adr/0025-variante-en-databricks-free-edition.md).

## Estructura

```
├── core/                 # núcleo: contrato, registro, bronze, Spark, calidad, warehouse, pipeline, CLI,
│                         # anomalías (core/anomaly) y correcciones (core/corrections)
├── connectors/<fuente>/  # connector.yaml + extractor.py + tests/fixtures
├── config/               # regiones (bbox y puntos), anomaly.yaml y corrections.yaml
├── dags/                 # DAG de Airflow
├── dbt/                  # staging → intermediate → marts, tests y seeds (ver dbt/README.md)
├── dashboards/           # provisioning y dashboards de Grafana
├── api/                  # API REST de solo lectura (FastAPI) y sus tests
├── web/                  # frontal web (React + Vite) que lee la API
├── docker/               # Dockerfiles de Airflow+Spark+dbt, de la API y de la web, init de Postgres
├── infra/terraform/      # AWS: S3, IAM, Glue Catalog, Athena y presupuesto, con tests sobre un AWS simulado
├── databricks/           # Databricks Free Edition: bundle del Lakeflow Job, tareas y paquete mdp_databricks
├── scripts/e2e.sh        # prueba de punta a punta (CI)
└── docs/
```

## CI/CD

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `ci.yml` | push a `main`/`develop`, PRs | ruff · el código compartido con Databricks compila con Python 3.12 · pytest con PySpark (cobertura de `core/` ≥ 80 %, ramas incluidas) · Terraform (`fmt`, `validate`, tflint y `terraform test` contra un AWS simulado) · sqlfluff · dbt build sobre Postgres vacío (slim CI en PRs) · build de la imagen + test de integridad del DAG. Las descargas van con caché y reintentos, así que una caída de GitHub de unos minutos no tumba la ejecución |
| `dbt-docs.yml` | push a `develop` | `dbt docs` en [GitHub Pages](https://alexandrecoll.github.io/MallorcaDataPlatform/), el [informe de cobertura](https://alexandrecoll.github.io/MallorcaDataPlatform/coverage/) del CI de ese commit con el badge del README, y manifest de `develop` para el slim CI |
| `e2e.yml` | PR a `main`, semanal | `docker compose up`, DAG dos veces con la API real, comprueba bronze/silver/gold e idempotencia |
| `release.yml` | tag `vX.Y.Z` (o a mano con un tag existente) | Release con notas del CHANGELOG + imágenes de Airflow y de la API REST en GHCR (`airflow:X.Y.Z` y `api:X.Y.Z`, también `X.Y`) |
| `pr-title.yml` | PRs | gitmoji + Conventional Commits en el título (`✨ feat(connector): ...`) |

Ramas y releases: [docs/git-workflow.md](docs/git-workflow.md) · Arquitectura y decisiones:
[docs/architecture.md](docs/architecture.md) · Plan completo: [ROADMAP.md](ROADMAP.md)

## Licencia

El código, MIT. Los datos pertenecen a sus dueños y se usan con sus licencias: la de cada fuente está en
[docs/data-governance.md](docs/data-governance.md).
