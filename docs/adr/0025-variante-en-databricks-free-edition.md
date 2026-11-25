# 0025 · Una variante en Databricks Free Edition con el mismo código de los conectores

- **Estado:** Aceptada
- **Fecha:** 2026-11-24

## Contexto

La fase 6 del [ROADMAP](../../ROADMAP.md) pedía una variante en Databricks. La idea inicial era un job que leyera el
mismo bronze, con Delta Lake en lugar de Parquet. Silver ya es Delta desde la [0016](0016-silver-en-delta.md), así
que lo que faltaba era ejecutar la plataforma en un servicio gestionado, con Unity Catalog y sin pagar nada.
Databricks Free Edition lo permite, con estas condiciones:

- **Solo cómputo serverless.** No se pueden crear clústeres propios. Cada entorno serverless fija la versión de
  Python, y todos los que ofrece, del 3 al 6, llevan **Python 3.12.3**. La pila local usa 3.14. El espacio de
  trabajo informaba de **Spark 4.2.0**.
- **Spark Connect.** No hay RDD. Los streams solo pueden usar disparadores que terminan solos (`availableNow`), y
  las funciones que se pasan a Spark (`foreachBatch`, UDF) se ejecutan en el servidor.
- **Salida a internet limitada a dominios de confianza.** Antes de decidir, desde un notebook del espacio de
  trabajo se probaron los hosts de las 15 fuentes y `pypi.org`: todos respondieron.
- **Uso no comercial** y una cuota diaria de cómputo.
- **El bronze local vive en MinIO, en `localhost`.** Databricks no puede leerlo sin exponerlo a internet.

## Decisión

- **Extraer dentro de Databricks con los mismos conectores.** El bundle sube `core/`, `connectors/` y `config/`
  junto al job (`sync.paths`), sin copiarlos. Cada respuesta se guarda como `payload.json` en un Volume de Unity
  Catalog, con las mismas claves que en MinIO.
- **Solo dos fuentes, las que no piden clave:** Open-Meteo y la EEA. Con ellas sale el sesgo del modelo CAMS frente
  a las estaciones.
- **Bronze con Auto Loader.** Una tabla Delta de solo añadir (`mallorca.bronze.payloads`), con
  `trigger(availableNow=True)`. Un Volume no versiona los ficheros, así que `cloudFiles.allowOverwrites` hace que
  una ventana descargada de nuevo cuente como fichero nuevo, igual que una versión nueva en MinIO.
- **Silver con el `normalize()` y las reglas de calidad del núcleo.** El esquema y las dos funciones de calidad
  pasan a `core/silver.py`, que solo importa PySpark: Databricks no carga boto3 ni psycopg. Las filas entran con un
  `MERGE` en la clave que no reescribe las que no cambian.
  - **Unity Catalog coordina las escrituras de la tabla gestionada**, así que sobra el bloqueo de Postgres.
  - **`loaded_payloads` hace el papel de `ops.ingestion_runs`.**
  - **Si dos payloads pendientes traen la misma clave, gana la descarga más reciente.**
- **Gold en Databricks SQL dentro del job:** cuatro tablas diarias con los mismos umbrales que los marts de dbt
  (18 horas por día de estación, 20 de tiempo, día local en Europe/Madrid).
- **Unity Catalog para el gobierno:**
  - un catálogo `mallorca` con los esquemas `bronze`, `silver` y `gold` y dos Volumes;
  - `USE CATALOG` para `account users`, y `USE SCHEMA` y `SELECT` solo sobre `gold`.
- **El job se describe como código:**
  - un bundle (`databricks/databricks.yml`) con el entorno serverless 6 fijado;
  - el horario definido pero en pausa;
  - una tarea `bronze` que se ejecuta con que una extracción acabe bien (`AT_LEAST_ONE_SUCCESS`).
- **Se despliega desde el terminal de quien lo usa, nunca desde GitHub.** La credencial queda en el perfil de la
  CLI, fuera del repositorio.
- **El CI compila el código compartido con Python 3.12.**

## Alternativas descartadas

- **Leer el bronze de MinIO desde Databricks.** Haría falta publicar MinIO en internet con credenciales. Es
  justo lo que la pila local evita.
- **Subir a mano los ficheros del bronze local.** Sería una carga puntual, no un pipeline: no tendría horario,
  ni idempotencia, ni manejo de fuentes caídas.
- **dbt-databricks para gold.** Reutilizaría los modelos, pero el proyecto de dbt está escrito para Postgres (sus
  macros y sus tipos), y añadiría una conexión a un SQL warehouse. Para cuatro tablas, el SQL dentro del job es menos
  maquinaria.
- **Lakeflow Declarative Pipelines (antes DLT).** Su modelo es declarar tablas a partir de streams. Los
  conectores normalizan cada payload con código Python del repositorio, y en ese modelo no encajan sin
  reescribirlos.
- **Silver con `foreachBatch`.** La función se ejecutaría en el servidor de Spark Connect, que tendría que importar
  el código del repositorio. La anti-join con `loaded_payloads` consigue lo mismo desde el cliente.
- **Desplegar desde el CI.** Pondría un token del espacio de trabajo personal en los secretos de GitHub. La
  Free Edition no es un entorno compartido que lo justifique.

## Consecuencias

- **A favor.**
  - Los conectores, la normalización y las reglas de calidad son las mismas en las dos pilas. Un cambio en un
    conector llega a las dos.
  - Los permisos se gestionan en Unity Catalog, por esquema y con `GRANT`, en lugar de con usuarios de Postgres.
  - La plataforma cuesta cero en los dos sitios.
- **En contra.**
  - **Gold está escrito dos veces**, en dbt y en SQL del job. Se mitiga con los mismos umbrales con nombre en
    `gold.py` y con pocas tablas.
  - **El código compartido queda atado a Python 3.12.** `compileall` en el CI detecta la sintaxis nueva, pero no
    una función de la biblioteca estándar que no exista en 3.12. Los tests corren en 3.14.
  - **El bronze guarda cada descarga de una misma ventana.** Tras tres ejecuciones había 114 filas para 38 ficheros.
    Es el historial que en MinIO guarda el versionado del bucket.
  - **Solo dos fuentes.** Las que piden clave (AEMET, REData, EMT…) necesitarían Databricks Secrets.

## Cuándo revisarla

- **Si los entornos serverless pasan a Python 3.13 o superior,** se puede subir el mínimo del código compartido y
  quitar el paso de 3.12 del CI.
- **Si gold crece más allá de unas pocas tablas,** compensa llevar los marts a dbt-databricks.
- **Si hiciera falta uso comercial,** habría que pasar a un espacio de trabajo de pago.
