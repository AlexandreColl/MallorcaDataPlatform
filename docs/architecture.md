# Caso de arquitectura: Mallorca Data Platform

Este documento cuenta la plataforma como un caso de arquitectura: qué problema resuelve, con qué restricciones, cómo
está montada y, sobre todo, **por qué** se eligió cada pieza y qué se descartó. El detalle de cada parte (conectores,
Delta, anomalías, correcciones, dashboards) está en el [README](../README.md); aquí solo se enlaza.

## 1. Contexto

**Problema.** Los datos abiertos de Mallorca están repartidos en una docena de organismos: tiempo (AEMET, SOCIB,
Open-Meteo), mar, aire (EEA, Govern), electricidad (REData), sismos (IGN), transporte (EMT, CTM), turismo
(SEGITTUR) y agua (Govern). Cada uno publica a su manera: JSON, CSV, Parquet, xlsx, ODS, PDF, GTFS o NetCDF, con
frecuencias de minutos a meses, retrasos de horas a meses, cortes y revisiones. La plataforma los reúne en un
esquema común, comprueba su calidad y responde preguntas que cruzan fuentes, por ejemplo: ¿aprieta el turismo al
agua?

**Restricciones**, que explican casi todas las decisiones:

| Restricción | Consecuencia |
|---|---|
| Coste cero y 100 % local | Todo corre en un `docker compose up` en un portátil; la nube se describe con Terraform, pero no se despliega. La variante en Databricks usa la Free Edition, también sin coste |
| ~8 GB de RAM para toda la pila | Spark en modo local, como mucho dos conectores a la vez y servicios opcionales tras perfiles de Compose |
| Fuentes poco fiables | Ninguna fuente puede tumbar a las demás; los días perdidos se recuperan solos |
| Datos que se revisan y llegan tarde | Toda escritura es idempotente: relanzar una ventana nunca duplica |
| Proyecto de portfolio, una sola persona | Piezas estándar del sector (Airflow, Spark, Delta, dbt), tests y CI desde el primer día, y cada decisión documentada y medida |

## 2. Vista general

```mermaid
flowchart LR
    SRC["20 fuentes abiertas"] --> AF
    subgraph AF["Airflow (con PySpark y dbt)"]
        direction TB
        ING["ingest<br/>una tarea por conector, 2 a la vez"] --> DET[detect_anomalies] --> COR[correct_values] --> DBT[dbt_build]
    end
    AF --> MINIO[("MinIO<br/>bronze · silver en Delta")]
    SRC -->|"BiciPalma, cada 5 min"| POLL["live_poll<br/>sin Spark"] --> MINIO
    AF --> PG[("PostgreSQL<br/>silver · quality · ops · gold")]
    PG --> GF["Grafana<br/>dashboards y alertas"]
    PG --> API["API REST<br/>solo lectura"] --> WEB["Web<br/>la isla en cifras"]
    AF -.->|OpenLineage| MQ["Marquez<br/>opcional"]
    MINIO -.->|"Terraform, sin desplegar"| AWS["S3 · Glue · Athena"]
    SRC -.->|"Open-Meteo y EEA,<br/>los mismos conectores"| DBX["Databricks Free Edition<br/>variante"]
```

| Capa | Dónde | Para qué |
|---|---|---|
| **bronze** | `s3://bronze/<fuente>/<dataset>/window=<desde>_<hasta>/payload.json`, y las instantáneas de las fuentes en vivo en `<fuente>/snapshots/<dataset>/day=<día>/<instante>.json` | Guardar la respuesta tal cual llegó, para poder reprocesar sin volver a llamar a la fuente |
| **silver** | Tabla Delta en `s3://silver/observations` y `silver.observations` en Postgres | Esquema común `source, entity, metric, ts, value, unit, quality, lat, lon`, con calidad marcada |
| **gold** | Esquema `gold` (dbt) | Hechos incrementales, marts por dominio con contrato y salud de las fuentes |
| **servicio** | Web, Grafana y FastAPI | La web para quien quiere ver la isla; Grafana para operar la plataforma; la API para leer gold desde un programa. Grafana y la API tienen su usuario de solo lectura, y la web solo habla con la API |

### Variante en Databricks

La misma plataforma, reducida, corre también en Databricks Free Edition ([detalle](../databricks/README.md),
[0025](adr/0025-variante-en-databricks-free-edition.md)). Es un Lakeflow Job descrito como bundle que importa
`connectors/`, `core/silver.py` y `config/` sin copiarlos, así que un cambio en un conector o en una regla de calidad
llega a las dos pilas.

| Pieza | Pila local | Databricks |
|---|---|---|
| Orquestación | Airflow, `mallorca_pipeline` | Lakeflow Job (`databricks/databricks.yml`), horario en pausa |
| Fuentes | 16 | 2, las que no piden clave: Open-Meteo y la EEA |
| bronze | MinIO, con versionado del bucket | Volume de Unity Catalog y Auto Loader a `mallorca.bronze.payloads` |
| silver | `MERGE` en Delta y upsert en Postgres | `MERGE` en `mallorca.silver.observations`, con las mismas reglas de calidad |
| gold | dbt en Postgres | Cuatro tablas diarias en Databricks SQL, entre ellas el sesgo del modelo CAMS frente a las estaciones |
| Acceso | Usuarios de Postgres de solo lectura | `GRANT` de Unity Catalog: `account users` solo lee `gold` |

No tiene anomalías, correcciones, API, web ni Grafana. Una ejecución de 3 días tarda unos 2 minutos y repetirla no
inserta ni actualiza nada.

### Una ejecución, paso a paso

```mermaid
sequenceDiagram
    autonumber
    participant AF as Airflow
    participant C as Conector
    participant B as bronze (MinIO)
    participant S as Spark (local)
    participant D as Delta silver
    participant P as Postgres
    AF->>C: ingest(conector, ventana de días completos)
    C->>C: ventana = día siguiente a la última carga correcta (catch-up)
    C->>B: PUT payload.json (clave determinista)
    C->>S: normalize() → filas del esquema común
    S->>S: reglas de calidad (marcan, no cambian valores)
    S->>P: pg_advisory_xact_lock(7303)
    S->>D: MERGE solo de filas nuevas o cambiadas
    S->>P: INSERT … ON CONFLICT … WHERE IS DISTINCT FROM
    S->>P: ops.ingestion_runs + quality.check_results
    AF->>P: detect_anomalies, correct_values (últimos 14 días)
    AF->>P: dbt build (incremental por updated_at)
```

Prueba real con 11 conectores y un día de ventana (noviembre de 2026): unos **8,5 minutos** desde la primera tarea
hasta el final de dbt. La ingesta tarda unos 5 minutos, dos conectores a la vez; después vienen la detección (57 s),
las correcciones (7 s) y `dbt build` (unos 2 min).

## 3. Decisiones

Cada decisión tiene su ADR en [docs/adr](adr/README.md): el contexto, lo que se decidió, las alternativas
descartadas, lo que cuesta y cuándo revisarla. Las sustituidas y las rechazadas se guardan, porque cuentan cómo
evolucionó la plataforma. Este es el resumen de las que están en vigor:

| ADR | Decisión | Por qué, en una línea |
|---|---|---|
| [0001](adr/0001-nucleo-fijo-y-conectores.md) | Núcleo fijo y conectores intercambiables | Una fuente nueva es una carpeta con su YAML, su extractor y sus tests; el núcleo y el DAG no cambian |
| [0002](adr/0002-medallion.md) | Medallion: bronze crudo, silver común, gold con dbt | Bronze versionado permite reprocesar sin volver a llamar a la fuente |
| [0003](adr/0003-idempotencia.md) | Idempotencia en todas las capas | Relanzar no duplica: ventanas de días completos, `MERGE` y upsert con `IS DISTINCT FROM` |
| [0004](adr/0004-spark-local-en-la-tarea.md) | Spark local dentro de la tarea de Airflow | Sin clúster, con el mismo código; el precio son unos 45 s fijos por conector |
| [0006](adr/0006-postgres-y-dbt.md) | Postgres como warehouse y dbt para gold | Un solo servicio sirve en milisegundos y guarda el estado; gold con incrementales y contratos |
| [0007](adr/0007-calidad-de-ingenieria.md) | Calidad de ingeniería y entrega | Fixtures reales grabados para los tests y un E2E semanal contra las APIs, que detecta cuando una fuente cambia |
| [0009](adr/0009-sismos-del-ign.md) | Sismos del IGN a través del FDSN de EMSC | Es la red nacional, con histórico y una API estándar |
| [0010](adr/0010-aislar-fallos-por-fuente.md) | Una fuente caída no para el resto | Una tarea por conector, reintentos solo en los cortes y catch-up de los días perdidos |
| [0011](adr/0011-marcar-no-es-corregir.md) | Marcar no es corregir | Calidad, anomalías y correcciones en tablas separadas; el valor original no se toca |
| [0013](adr/0013-calidad-del-aire-de-la-eea.md) | Calidad del aire de la EEA | Es la fuente oficial, con todas las horas, en Parquet y sin clave |
| [0014](adr/0014-servir-gold.md) | Servir gold: Grafana como código y una API pequeña | Dashboards revisables en los PR y roles de solo lectura por consumidor |
| [0015](adr/0015-local-primero-nube-descrita.md) | Local primero, nube descrita con Terraform | El camino a AWS probado contra un proveedor simulado, sin coste |
| [0016](adr/0016-silver-en-delta.md) | Silver en Delta Lake | El lake pasa de 67.000 ficheros a 12, con historial, *time travel* y `MERGE` |
| [0017](adr/0017-observabilidad-y-linaje.md) | Observabilidad y linaje | Las alertas leen el estado de las tablas; un solo grafo de linaje de la ingesta a gold |
| [0018](adr/0018-sin-cache-de-extraccion.md) | Sin caché aparte (Redis) | Bronze ya hace de caché, y extraer cuesta 1 s de los 45 s que tarda cada conector |
| [0019](adr/0019-frontal-web-sobre-la-api.md) | Un frontal web propio sobre la API | La isla en cifras para quien no opera la plataforma; solo lee la API, así que no toca el warehouse |
| [0020](adr/0020-gobierno-del-dato-en-el-catalogo-de-fuentes.md) | El gobierno del dato vive en el catálogo de fuentes | Dueño, licencia, acceso y SLA en la misma fila que la fuente, obligatorios por tests de dbt y evaluados en `gold.source_health` |
| [0021](adr/0021-solo-los-dias-que-faltan.md) | Un DAG diario que solo descarga los días que faltan | Si no falta ningún día, no se llama a la fuente ni se arranca Spark |
| [0022](adr/0022-fuente-caida-no-es-un-fallo.md) | Una fuente caída no es un fallo de la plataforma | El estado `unavailable` separa los cortes de la fuente de los errores propios, que son los únicos que alertan |
| [0023](adr/0023-cache-y-limite-en-el-proceso-de-la-api.md) | Caché y límite de peticiones en cada proceso de la API | Gold cambia una vez al día; sin un almacén compartido que mantener |
| [0024](adr/0024-la-web-en-tres-idiomas.md) | La web en castellano, catalán e inglés | El idioma en la URL y diccionarios tipados: `tsc` falla si falta un texto |
| [0025](adr/0025-variante-en-databricks-free-edition.md) | Una variante en Databricks Free Edition | Los mismos conectores y reglas de calidad en un lakehouse gestionado con Unity Catalog, sin coste |
| [0026](adr/0026-fuentes-en-vivo-sin-historico.md) | Una fuente sin histórico se sondea cada 5 minutos y su serie sale de bronze | BiciPalma solo publica su estado actual: un sondeo sin Spark guarda instantáneas en bronze y el conector diario las resume por hora |

Sustituidas y rechazadas:

- **Silver en Parquet por fuente y día** ([0005](adr/0005-silver-en-parquet.md)), sustituida por 0016.
- **Sismos de USGS** ([0008](adr/0008-sismos-de-usgs.md)), sustituida por 0009: 0 eventos en un año en la zona.
- **Calidad del aire de OpenAQ** ([0012](adr/0012-calidad-del-aire-de-openaq.md)), rechazada: republica las
  mismas estaciones con un 30 % de las horas.

## 4. Atributos de calidad

| Atributo | Mecanismo |
|---|---|
| Idempotencia | Claves deterministas, `MERGE` y upsert con `IS DISTINCT FROM`, recalcular y reemplazar ventanas; E2E con doble ejecución |
| Resiliencia | Tareas aisladas por fuente, reintentos solo para cortes, catch-up, `all_done` |
| Auditabilidad | Bronze versionado, historial y Change Data Feed de Delta, `run_id` en cada fila, calidad y correcciones en tablas propias |
| Observabilidad | `ops.ingestion_runs`, `quality.check_results`, alertas de Grafana con aviso por Telegram, linaje OpenLineage |
| Coste | 0 en local; en AWS, el lake cuesta céntimos al mes (presupuesto de 2 USD y 1 GB como máximo por consulta en Athena) y el gasto real es el cómputo siempre encendido ([sección 5](#5-trade-offs-costes-y-escalado)) |
| Seguridad | Roles de Postgres de solo lectura, claves en `.env` fuera del repo, IAM sin comodines, buckets privados, cifrados y solo TLS |
| Extensibilidad | Contrato de conector, YAML de métricas y reglas, staging de dbt de una línea con una macro común |
| Reproducibilidad | Una sola imagen para Airflow, Spark y dbt (dbt en su propio venv), versiones fijadas, `make up` |

## 5. Trade-offs, costes y escalado

Cada decisión de la sección 3 vale para el tamaño de hoy. Esta sección dice qué se paga por ella, a partir de qué
tamaño deja de valer y qué la sustituiría.

### Volumen de hoy

Medido sobre la pila local el 3 de noviembre de 2026:

| Medida | Valor |
|---|---|
| Fuentes y series | 12 fuentes, 3.910 series (fuente, entidad, métrica) |
| Silver | 9,1 millones de filas; el 87 % es histórico de calidad del aire (Govern 2002-2021 y EEA desde 2021) |
| Carga diaria | Unas 3.900 filas por ejecución, 10.100 como máximo: unos 1,4 millones al año |
| Postgres | 5,9 GB: silver 2,6 GB y gold 3,3 GB (`fct_observations` repite silver con sus propios índices) |
| MinIO | Bronze 0,5 GB y silver en Delta 1,2 GB, con las versiones que aún no ha borrado `VACUUM` |
| Tiempo de una ejecución | 8,5 min, de los que unos 45 s por conector son fijos (arrancar Spark y leer Delta, [0004](adr/0004-spark-local-en-la-tarea.md)) |

La plataforma es pequeña en datos y grande en número de fuentes. Por eso lo primero que se rompe al crecer es el
coste fijo por conector, no el volumen.

### Lo que se gana, lo que se paga y cuándo cambiarlo

| Decisión | Se gana | Se paga | Se revisa cuando… | Por qué se cambiaría |
|---|---|---|---|---|
| Spark local, uno por tarea ([0004](adr/0004-spark-local-en-la-tarea.md)) | Ningún clúster que mantener; el mismo código que en un clúster | Unos 45 s fijos por conector, aunque traiga 10 filas | Hacia 30 fuentes, cuando la ingesta pasa del cuarto de hora | Un servidor Spark Connect compartido; en la nube, EMR Serverless o Glue |
| Un lock para todos los escritores de Delta ([0016](adr/0016-silver-en-delta.md)) | Commits correctos sobre S3 sin DynamoDB | Los commits y la compactación van en fila, de 8 a 25 s cada uno | Más de dos escritores a la vez (hoy son dos) | Compactar fuera del lock (`OPTIMIZE` periódico) y, en AWS, el LogStore de DynamoDB |
| Silver en Delta y en Postgres ([0002](adr/0002-medallion.md)) | Lake auditable y consultas en milisegundos | Doble escritura y 2,6 GB repetidos | El warehouse pasa a un motor que lea el lake | Athena (o Redshift Spectrum) sobre Delta; Postgres solo para marts pequeños |
| Esquema largo, una fila por valor ([0001](adr/0001-nucleo-fijo-y-conectores.md)) | Una fuente nueva no toca ni el núcleo ni el esquema | Los marts tienen que pivotar; los datos que no son series se resumen | Hacen falta tipos que no son números (texto, geometría) | Tablas anchas por dominio en silver, con el esquema largo solo para las series |
| Postgres como warehouse ([0006](adr/0006-postgres-y-dbt.md)) | Un solo servicio para dbt, Grafana, la API y el estado | Almacenamiento por filas: gold ocupa más que silver | Gold pasa de unos 100 millones de filas o las consultas de Grafana tardan segundos | Particionar `fct_observations` por mes; después, un motor columnar con el mismo dbt |
| Lotes diarios ([0026](adr/0026-fuentes-en-vivo-sin-historico.md) para las fuentes en vivo) | Ventanas de días completos, idempotencia simple | Un día de retraso, también en BiciPalma, que se sondea cada 5 minutos | Alguien necesita actuar en minutos sobre una fuente en vivo | Cargar cada hora desde bronze, o un consumidor en streaming que escriba las mismas instantáneas |
| Recalcular 14 días de anomalías y correcciones ([0003](adr/0003-idempotencia.md)) | Sin estado incremental que mantener | Se repite trabajo cada día (57 s) | Muchas más series: el tiempo crece con series × días | Recalcular solo las series que cambiaron (el Change Data Feed de Delta ya lo dice) |

### Qué se rompe primero al crecer

| Escala | Ejemplo | Qué se rompe | Qué se cambia |
|---|---|---|---|
| **1×** (hoy) | 12 fuentes, 9 M filas | Nada; la ingesta se lleva 5 de los 8,5 min | — |
| **10× fuentes** | 120 fuentes, mismo volumen por fuente | La ingesta pasa a unos 50 min con dos tareas a la vez. Con más tareas a la vez, la compactación dentro del lock de Delta suma por sí sola de 16 a 50 min en fila | Spark Connect compartido, compactación fuera del lock, más tareas en paralelo |
| **10× volumen** | 90 M filas en silver | Postgres ronda los 60 GB y los paneles que leen `fct_observations` se vuelven lentos | Particionar por mes en Postgres; Grafana lee agregados, no hechos |
| **100×** | 900 M filas, cientos de fuentes | Postgres ya no sirve como warehouse analítico y un solo nodo de Airflow no basta | Gold en un motor columnar (Athena, Redshift Serverless, BigQuery o Snowflake, con el mismo dbt), Spark en un servicio gestionado y Postgres solo para servir marts y el estado operativo |

Lo que no cambia en ninguna escala: el contrato de conector, bronze, la clave de silver, la idempotencia y el
`MERGE`. Son las decisiones caras de cambiar, y por eso se tomaron pensando en el tamaño grande.

### Costes en AWS

Estimación con precios de lista de AWS en US East (noviembre de 2026). En la región de España (`eu-south-2`) son
algo más altos; la cifra exacta sale de la calculadora de AWS.

| Pieza | Hoy (1×) | 10× volumen |
|---|---|---|
| S3: bronze y silver, unos 2 GB | Unos 0,05 USD/mes | Unos 0,5 USD/mes |
| Athena, 5 USD por TB leído | Una consulta que lee todo silver: menos de 0,01 USD. Con el límite de 1 GB por consulta, mil consultas al mes no pasan de 5 USD | Igual, si las consultas filtran por fuente y fecha; si no, crece con los datos |
| Glue Data Catalog | 0 (gratis hasta un millón de objetos) | 0 |
| Airflow gestionado (MWAA, entorno pequeño) | Unos 360 USD/mes (0,49 USD/h, encendido siempre) | Igual |
| Toda la pila en una EC2 de 8 GB con el mismo Compose | Unos 50 USD/mes | Hay que separar el warehouse |
| Postgres gestionado (RDS pequeño) | Entre 15 y 30 USD/mes | Entre 60 y 120 USD/mes |

La conclusión cambia el diseño en la nube. El lake (S3, Glue y Athena) cuesta céntimos porque se paga por uso. Lo
que cuesta es el cómputo siempre encendido, y sobre todo el orquestador. Para un DAG que trabaja unos 10 minutos al
día, mantener MWAA encendido cuesta decenas de veces lo que el lake, incluso con mil consultas al mes en Athena. Por eso el camino a la nube va en este
orden:

1. Primero, el lake, que es casi gratis (lo que ya describe `infra/terraform`).
2. Después, el cómputo por uso: Spark como job (EMR Serverless o Glue) y un orquestador que cobre por tarea, como
   MWAA Serverless.
3. Solo con usuarios de verdad, un warehouse siempre encendido.

## 6. Limitaciones y siguientes pasos

- **Arranque de Spark por tarea.** Es la mayor parte del tiempo de ingesta. Siguiente paso: un servidor Spark
  Connect compartido.
- **Un escritor a la vez en Delta.** El lock serializa los commits y la compactación. Basta para dos conectores a
  la vez, no para decenas.
- **Silver duplicado** en Delta y en Postgres. En AWS, Athena sobre Delta podría sustituir a la copia de Postgres.
- **Gold escrito dos veces** en la variante de Databricks: en dbt y en el SQL del job. El código compartido queda
  además atado a Python 3.12, que es lo que llevan los entornos serverless.
- **Contaminantes muy locales** (NO₂, CO, partículas): casi nunca tienen una fuente de apoyo correlacionada. El NO₂
  y el CO se corrigen con el perfil semanal de la propia estación, porque los mueve el tráfico; las partículas no,
  porque las mueve el tiempo, y sus huecos largos se quedan sin corregir a propósito.
- **Detectores.** El residuo estacional ve el 61 % de los desfases horarios, pero las derivas casi solo donde acaban;
  un sensor congelado en un valor normal para esa hora sigue escapándose a la mitad de las veces.

Modelo de datos: [data-model.md](data-model.md) · Decisiones: [adr](adr/README.md) · Plan completo:
[ROADMAP.md](../ROADMAP.md) · Historial de cambios: [CHANGELOG.md](../CHANGELOG.md)
