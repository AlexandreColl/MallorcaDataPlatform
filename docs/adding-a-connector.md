# Añadir un conector (objetivo: ≤ 1 día)

1. **Probar la API a mano** y anotar en un issue (`Nuevo conector`): URL, autenticación, frecuencia,
   cobertura en Mallorca, ejemplo de respuesta.
2. Rama: `git switch develop && git switch -c feature/connector-<nombre>`.
3. Crear la carpeta con `make new-connector NAME=<nombre>`. Escribe esto, con el conector desactivado
   (`enabled: false`), un dataset y una métrica de ejemplo, y un extractor que pide la ventana a una API JSON y lee
   una lista de registros:

```
connectors/<nombre>/
├── __init__.py
├── connector.yaml        # datasets, métricas, unidades, rangos válidos, secretos
├── extractor.py          # clase que hereda de BaseConnector
├── README.md             # qué datos trae y sus limitaciones
└── tests/
    ├── fixtures/         # respuestas REALES: make record-fixtures (más abajo)
    └── test_<nombre>.py  # reproduce las grabaciones y comprueba que cada valor encaja con el YAML
```

4. `connector.yaml`: el campo `name` debe coincidir con la carpeta. `frequency` alimenta la regla de
   huecos (`1h`, `1d`…); si los datasets tienen granularidades distintas, cada uno puede declarar la suya
   (`datasets.<x>.frequency`, ver `connectors/redata`). `catch_up_days` (por defecto `max_days`) limita cuánto se
   alarga una ventana para recuperar días de ejecuciones fallidas; bájalo si la fuente no guarda tanto histórico
   (SOCIB: 28). Si la API sirve más histórico que eso, `recover_days` (por defecto `catch_up_days`) recupera un
   hueco más largo en ejecuciones extra de `catch_up_days` días, de la más antigua a la más reciente (AEMET: 1095,
   REData: 366); no lo subas si la API no sirve esos días, o cada ejecución fallaría. `lag_days` retrasa el final de la ventana para fuentes que publican tarde (AEMET: 3).
   Para estadísticas mensuales usa `frequency: 1mo` (un valor por mes, fechado el día 1) y `min_days` para que
   cada ejecución cubra meses ya publicados (ver `connectors/dataestur`). Las anuales usan `frequency: 1y` (un valor
   por año, fechado el 1 de enero; ver `connectors/ine_population`).
   Para fuentes de eventos sin muestreo regular (sismos…)
   usa `frequency: event`: no se aplica la regla de huecos y una ventana sin eventos no es un error (ver
   `connectors/ign`); añádela también a `vars.event_sources` en `dbt/dbt_project.yml` y a `EVENT_SOURCES` en
   `scripts/e2e.sh`. Añade el conector a `CONNECTORS` en `scripts/e2e.sh`. `secrets` lista las variables que deben estar en `.env` (pásalas también en `x-platform-env` de
   `docker-compose.yml`); sin ellas el conector queda fuera de la selección por defecto del DAG.
   Si la API limita el rango por petición, trocea con `window.split(max_days)` y genera un payload por trozo.
   Si la fuente solo publica su estado actual (sin histórico), es una **fuente en vivo**: declara `poll_every` en
   cada dataset que haya que sondear y extiende `LiveConnector` (`core/connectors/live.py`) con `poll`, `instant` y
   `aggregate` en lugar de `extract` y `normalize`. El DAG `live_poll` guarda las instantáneas en bronze y la
   ejecución diaria las lee de ahí (ver `connectors/bicipalma` y el
   [ADR 0026](adr/0026-fuentes-en-vivo-sin-historico.md)). No va en `CONNECTORS` de `scripts/e2e.sh`: la ventana de
   la E2E es anterior a su primera instantánea.
5. `extractor.py` implementa dos métodos:
   - `extract(window, region) -> list[RawPayload]`: llama a la API y devuelve la respuesta **sin tocar**.
   - `normalize(payload, region) -> Iterable[Observation]`: convierte al esquema común.
     Filtra por `region.contains(lat, lon)` si la fuente es de puntos (estaciones, boyas).
   - Si la fuente trae su propio control de calidad, emite `quality="suspect"` en las observaciones dudosas: la
     regla `source_qc` lo conserva y lo cuenta (ver `connectors/socib`).
   - Si un dataset se pide en varias peticiones por ventana (una por estación…), usa `RawPayload(partition=...)`
     para que cada respuesta tenga su propio objeto en bronze.
   - Para respuestas que no son JSON (CSV, XML) usa `self.http.get_text`.
   - Opcional: `describe(payload, region) -> Iterable[Entity]` da el nombre de las entidades del payload (el
     `stop_name` de un GTFS, el `nombre` de un inventario, el `name` de las estaciones de `connector.yaml`). El
     pipeline lo guarda en `silver.entities` y la API lo devuelve como `name`. Sin él, la web enseña el identificador.
   - Opcional, solo para redes de transporte: `routes(payload, region) -> Iterable[Route]` da las líneas con su
     recorrido. El pipeline sustituye con ellas las de la fuente en `silver.routes` (ver `core/connectors/gtfs.py`).
6. **Grabar las respuestas reales**: `make record-fixtures CONNECTOR=<nombre> DAYS=1`. Ejecuta el `extract` del
   conector con la API de verdad (con las claves del `.env`), guarda cada respuesta en `tests/fixtures/` y escribe
   `recorded.json`, que guarda la ventana, la región y, por cada petición, su URL, sus parámetros y su fichero.
   Los tests las reproducen con `RecordedHttp` (`core/connectors/recording.py`), sin red. Una petición que no se
   grabó falla, así que si el conector cambia lo que pide, el test lo dice. Para regrabar, se repite el comando:
   solo se sustituyen `recorded.json` y los ficheros que lista, y si la grabación falla, las anteriores se
   conservan. Una respuesta de más de 2 MB detiene la grabación (`--max-mb`), porque las fixtures van en git. Para
   fuentes de eventos, graba una ventana larga (`DAYS=90`): un día tranquilo no trae ninguno. El test generado
   comprueba que cada valor tiene una métrica del YAML, con su unidad, dentro de la ventana y de su rango; añade los
   tuyos (ver `connectors/open_meteo/tests/`).
7. Añadir una fila a `dbt/seeds/dim_sources.csv`: nombre visible en el selector de fuentes de Grafana, tipo de
   datos y la ficha de gobierno, que incluye el dueño, la licencia, el acceso, los datos personales y el SLA
   ([data-governance.md](data-governance.md) dice cómo fijarlo). Los tests de dbt fallan si una fuente de silver no
   tiene fila o si a su ficha le falta un campo.
8. Probar de punta a punta: `make run CONNECTORS=<nombre> DAYS=1` y mirar Grafana.
9. Sección en el README, entrada en `CHANGELOG.md` → PR `✨ feat(connector): add <nombre>`.

No hace falta tocar el núcleo, el DAG ni dbt: el registro descubre el conector, el DAG lo ofrece como
parámetro y los modelos gold lo incluyen automáticamente.
