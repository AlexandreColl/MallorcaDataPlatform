# Variante en Databricks Free Edition

La misma plataforma, en un espacio de trabajo gratuito de Databricks. Es un Lakeflow Job (un job de Databricks con
varias tareas encadenadas) que:
- descarga Open-Meteo y la calidad del aire de la EEA (Agencia Europea de Medio Ambiente) con **los mismos
  conectores** que el DAG de Airflow;
- guarda bronze, silver y gold en tablas Delta de Unity Catalog (el catálogo de datos y permisos de Databricks);
- construye cuatro tablas gold, entre ellas el sesgo del modelo CAMS (el servicio de calidad del aire de
  Copernicus, que Open-Meteo sirve) frente a las estaciones.

La pila local de Docker Compose no cambia. La decisión y sus alternativas están en la
[ADR 0025](../docs/adr/0025-variante-en-databricks-free-edition.md).

```mermaid
flowchart LR
    subgraph Job["Lakeflow Job mallorca_pipeline (serverless, entorno 6)"]
        direction LR
        S[setup<br/>catálogo, esquemas,<br/>Volumes, GRANT] --> E1[extract_open_meteo]
        S --> E2[extract_eea_air_quality]
        E1 --> B[bronze<br/>Auto Loader]
        E2 --> B
        B --> SV[silver<br/>normalize + calidad<br/>+ MERGE]
        SV --> G[gold<br/>Databricks SQL]
    end
    E1 -. payload.json .-> V[(Volume<br/>mallorca.bronze.raw)]
    E2 -. payload.json .-> V
    V --> B
    B --> TB[(mallorca.bronze.payloads)]
    SV --> TS[(mallorca.silver.observations)]
    G --> TG[(mallorca.gold.*)]
```

## Local frente a Databricks

| Pieza | Local (Docker Compose) | Databricks Free Edition |
|---|---|---|
| Orquestación | DAG de Airflow | Lakeflow Job descrito en [databricks.yml](databricks.yml), un Declarative Automation Bundle (antes Databricks Asset Bundle) |
| Cómputo | PySpark en modo local dentro de la tarea, Python 3.14 | Serverless con Spark Connect, entorno 6: Python 3.12.3 y Spark 4.2.0 |
| Fuentes | Las 15 del catálogo | Open-Meteo y la EEA, las dos que no piden clave |
| Bronze | Objetos `payload.json` en MinIO, con versionado del bucket | Los mismos `payload.json`, con las mismas claves, en el Volume `mallorca.bronze.raw`. Auto Loader los añade a la tabla `mallorca.bronze.payloads`, una fila por fichero leído |
| Silver | Tabla Delta en MinIO con `MERGE` y un bloqueo en Postgres | Tabla gestionada `mallorca.silver.observations` con el mismo `MERGE`. Unity Catalog coordina las escrituras, así que no hace falta bloqueo |
| Calidad | `core/quality`, resultados en Postgres | El mismo motor (`core/silver.py`), resultados en `mallorca.silver.check_results` |
| Registro de cargas | `ops.ingestion_runs` | `mallorca.silver.loaded_payloads`: qué payload cargó silver, y en qué ejecución |
| Gold | dbt sobre Postgres | Cuatro tablas en Databricks SQL ([gold.py](src/mdp_databricks/gold.py)) con los umbrales de los marts de dbt |
| Permisos | Usuarios de Postgres | `GRANT` de Unity Catalog: `account users` puede usar el catálogo y leer solo el esquema `gold` |
| Coste | 0 | 0, dentro de la cuota diaria de la Free Edition |

## Qué hay en la carpeta

| Fichero | Qué hace |
|---|---|
| `databricks.yml` | El bundle: sube `core/`, `connectors/` y `config/` con el job, sin copiarlos, y define las seis tareas, el entorno serverless 6 y un horario diario (6:00, Europe/Madrid) en pausa |
| `tasks/main.py` | Punto de entrada de cada tarea: `main.py <paso> --catalog mallorca [...]` |
| `src/mdp_databricks/catalog.py` | Nombres de Unity Catalog y el `setup`: catálogo, esquemas, Volumes, tablas y `GRANT`, todo `IF NOT EXISTS` |
| `src/mdp_databricks/volume_store.py` | El bronze sobre el Volume, con la misma interfaz que el de MinIO |
| `src/mdp_databricks/bronze.py` | Auto Loader con `availableNow`: lee los ficheros nuevos y se para |
| `src/mdp_databricks/silver.py` | Los payloads que silver aún no ha cargado, normalizados por su conector, etiquetados y unidos con `MERGE` |
| `src/mdp_databricks/gold.py` | Las cuatro tablas gold |
| `tests/` | Tests con la SparkSession local de la plataforma; corren con el resto (`make test`) |

## Cómo ejecutarlo

Necesitas una cuenta de Databricks Free Edition y la CLI de
Databricks (su herramienta de línea de comandos). Estos son los pasos que se siguieron, desde WSL (Debian) y con la
CLI v1.28.0.

1. Instala la CLI:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sudo sh
   ```

2. Inicia sesión con un perfil propio. El host es la dirección de tu espacio de trabajo, hasta
   `.cloud.databricks.com`. El comando muestra una URL que hay que abrir en el navegador para autorizar el acceso
   (OAuth). La credencial queda en `~/.databrickscfg` y en `~/.databricks/`, fuera del repositorio:

   ```bash
   databricks auth login --host https://<tu-espacio>.cloud.databricks.com --profile mallorca
   ```

3. Desde esta carpeta, valida, despliega y lanza el job:

   ```bash
   cd databricks
   databricks bundle validate -p mallorca
   databricks bundle deploy -p mallorca
   databricks bundle run mallorca_pipeline -p mallorca
   ```

`bundle run` espera a que acaben las seis tareas y muestra el registro de cada una. El job crea lo que necesita
en la primera tarea, así que no hay que preparar nada en el espacio de trabajo. El catálogo (`mallorca`), el grupo
lector (`account users`) y los días (`3`) son variables de `databricks.yml`. La ejecución documentada usó los
valores por defecto.

El bundle no nombra ningún espacio de trabajo: el host y la credencial salen del perfil. `.databrickscfg` y las
carpetas `.databricks/` están en `.gitignore`.

Si el repositorio es un *worktree* de git creado en Windows y la CLI corre en WSL, la CLI no puede leer `.git` (su
ruta es de Windows) y `validate` falla. Copiar `core/`, `connectors/`, `config/` y `databricks/` a una carpeta de
WSL y desplegar desde allí lo resuelve.

## Lo que dio la ejecución

Ventana del 21 al 23 de noviembre de 2026 (`days` = 3, hasta el último día publicado), el 24 de noviembre:

| Tarea | Resultado |
|---|---|
| `setup` | Catálogo `mallorca` con sus tres esquemas, dos Volumes, cuatro tablas y los `GRANT` |
| `extract_open_meteo` | 2 payloads: calidad del aire (modelo CAMS) y tiempo, de 6 puntos de la isla |
| `extract_eea_air_quality` | 36 payloads, uno por estación y contaminante. 8 estaciones de Baleares que no están en `connector.yaml` se ignoran, con aviso en el registro |
| `bronze` | 38 ficheros nuevos en `mallorca.bronze.payloads` |
| `silver` | 6.912 filas: 2.592 de la EEA (2.485 `ok`, 15 `suspect`, 92 `missing`) y 4.320 de Open-Meteo, todas `ok` |
| `gold` | `air_quality_daily` 203 filas, `station_model_pairs` 9, `air_quality_model_bias_daily` 76, `weather_daily` 24 |

Cada ejecución completa tardó entre 1 min 44 s y 2 min 6 s.

**Relanzar la misma ventana no cambia nada.** La segunda ejecución con el mismo código volvió a descargar los 38
payloads, y bronze los añadió como una descarga más. Silver los normalizó y el `MERGE` acabó con 0 filas
insertadas y 0 actualizadas. Gold quedó con las mismas filas.

Sesgo medio del modelo CAMS frente a las estaciones (modelo − estación, en µg/m³), sobre los días de estación con
18 horas válidas o más:

| Contaminante | Días de estación | Sesgo medio |
|---|---|---|
| NO₂ | 26 | 0,19 |
| O₃ | 26 | −4,66 |
| PM10 | 19 | −2,46 |
| PM2,5 | 5 | −1,24 |

Son tres días y nueve estaciones: sirven para comprobar que la cadena funciona, no como resultado. El sesgo del
histórico completo está en `fct_air_quality_model_bias_daily` de la pila local.

Para consultar las tablas, usa el editor SQL del espacio de trabajo:

```sql
SELECT station, model_point, distance_km, local_date, station_mean_ugm3, model_mean_ugm3, bias_ugm3
FROM mallorca.gold.air_quality_model_bias_daily
WHERE metric = 'pm10'
ORDER BY station, local_date;
```

## Lo que hubo que cambiar al ejecutarlo de verdad

Los tests locales no podían cubrir tres cosas, y la primera ejecución en serverless las sacó:

- **`__file__` no existe en un `spark_python_task`.** Serverless ejecuta el fichero con `exec()`. `main.py` toma su
  ruta del código compilado, que la conserva.
- **El progreso de un stream `availableNow` puede dejar `numInputRows` vacío con Spark Connect.** Bronze cuenta las
  filas que gana la tabla, que es de solo añadir.
- **Los payloads pendientes se acumulan.** Una ejecución que cae entre bronze y silver deja sus payloads para la
  siguiente, que trae los suyos de la misma ventana. Juntos, todas sus filas tenían clave repetida y la regla
  `duplicate` las marcaba como `suspect`, así que gold salía vacío. Ahora gana la descarga más reciente de cada clave,
  como la última versión de un objeto en MinIO, y la regla sigue detectando una clave repetida dentro de un mismo
  payload.

## Límites

- **Solo dos fuentes.** Las que piden clave (AEMET, REData, EMT…) necesitarían Databricks Secrets y no están
  conectadas.
- **Gold está escrito dos veces**: en dbt para la pila local y en SQL aquí. Los umbrales son los mismos y tienen
  nombre propio en `gold.py`.
- **El código compartido debe funcionar en Python 3.12**, que es lo que traen todos los entornos serverless, del 3
  al 6. El CI lo compila con 3.12 (`compileall`). Eso detecta la sintaxis nueva, pero no una función de la
  biblioteca estándar que no exista en 3.12.
- **El horario está en pausa.** La Free Edition tiene una cuota diaria de cómputo, y el modo `development` del
  bundle también lo pausa. Las ejecuciones son a mano, con `bundle run`.
- **La Free Edition no admite uso comercial.**
