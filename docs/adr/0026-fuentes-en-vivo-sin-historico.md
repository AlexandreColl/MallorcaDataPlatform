# 0026 · Una fuente sin histórico se sondea cada 5 minutos y su serie sale de bronze

- **Estado:** Aceptada
- **Fecha:** 2026-11-26

## Contexto

BiciPalma, la bici pública de Palma, solo publica su estado actual: bicis y anclajes libres por estación en este
momento. No hay ninguna API que devuelva el de ayer. Todas las fuentes anteriores sirven ventanas del pasado, y la
plataforma está construida sobre eso:

- **El DAG diario** pide a cada conector una ventana de días completos (`extract(window, region)`), con `only_missing`,
  `lag_days` y el *catch-up* ([ADR 0003](0003-idempotencia.md), [ADR 0021](0021-solo-los-dias-que-faltan.md)).
- **La regla de huecos** espera un valor por paso de `frequency` en toda la ventana.
- **`source_health`** cuenta como fallo cada ejecución que no carga.

Con una fuente así, la serie solo existe si alguien guarda el estado mientras pasa. Y el portátil tiene 16 GB: lo que
corra cada pocos minutos no puede arrancar Spark.

Antes de diseñar se probaron las dos vías de acceso (2026-11-26):

- **El GBFS del operador.** Nextbike publica el feed estándar del sistema `nextbike_ea` (BiciPalma) en
  `gbfs.nextbike.net/maps/gbfs/v2/nextbike_ea/`, en GBFS 2.3, sin clave y con licencia **CC0-1.0** declarada en su
  `system_information.json`. `station_status` trae, por estación, las bicis por tipo (eléctricas aparte) y `last_reported`.
- **CityBikes** (`api.citybik.es/v2/networks/bicipalma`). Devuelve los mismos números con los mismos identificadores
  (su `extra.uid` es el `station_id` de GBFS), porque los saca del feed de Nextbike. No declara licencia: sus términos
  piden citar el proyecto y advierten de que «no es exactamente open data».

## Decisión

- **La fuente es el GBFS de Nextbike, sin respaldo de CityBikes.** CityBikes no es independiente: lee el mismo feed, así
  que cae con él, y añadiría un segundo formato sin licencia clara a cambio de nada.
- **Un sondeo ligero guarda el estado en bronze.** El DAG `live_poll` corre cada 5 minutos, el `poll_every` más corto
  de las fuentes en vivo (`MDP_LIVE_SCHEDULE` lo cambia o lo apaga). Hace peticiones HTTP y escrituras en MinIO, sin
  Spark ni Postgres, y es lo único que llama a la fuente.
  - Cada respuesta se guarda sin tocar como una *instantánea*. Su clave es determinista:
    `<fuente>/snapshots/<dataset>/day=<día UTC>/<instante>.json`, y el instante es el sello de la propia fuente
    (`last_updated`), no la hora de la petición. Sondear un feed que no ha cambiado reescribe la misma clave.
  - Cada dataset declara su periodo en el YAML: `station_status` cada 5 minutos y `station_information`, que casi no
    cambia, una vez por hora. Un periodo que ya tiene instantánea no se vuelve a pedir.
  - Los sondeos no se registran en `ops.ingestion_runs`: serían 288 filas al día. Un sondeo perdido se ve donde
    importa, como un hueco en la serie horaria.
- **El conector diario lee su ventana de bronze, no de la API.** Un conector en vivo hereda de `LiveConnector`
  (`core/connectors/live.py`):
  - Su `extract` lista las instantáneas de los días de la ventana y devuelve sus claves en un manifiesto. Su
    `normalize` las lee y las resume por estación y hora UTC: media, mínimo y máximo de las bicis libres y de los
    anclajes libres, media de las eléctricas y ocupación media.
  - Todo lo demás es igual que en el resto de conectores: ventanas, *catch-up*, `only_missing`, calidad, Delta y
    Postgres. Bronze guarda todas las instantáneas, así que un día que el DAG diario no cargó se recupera siempre
    (`recover_days: 31`).
- **Las horas sin sondeo posible no son huecos.** El núcleo gana dos ganchos con valor por defecto neutro:
  - `first_day()`: el día de la primera instantánea. La ventana empieza ese día, y una ventana anterior entera se salta
    sin registrar ejecución. Así no cuenta ni como carga ni como fallo en `source_health`.
  - `observed_span(payload)`: desde la hora de la primera instantánea hasta la hora en curso al leer la ventana. La
    regla de huecos solo espera los pasos de ese tramo.
- **Un día leído antes de acabar sigue faltando.** `missing_days` ya no da por cargado un día que una ejecución
  correcta empezó antes de que terminara. Vale para todas las fuentes, aunque solo una ejecución manual de hoy lo
  provocaba hasta ahora: la siguiente ejecución lo relee entero.
- **Es el primer paso del extra «MQTT / streaming»** del ROADMAP: una fuente casi continua entra por un sondeo que
  aterriza en bronze. MQTT no se construye. Si llegara una fuente que empuja mensajes, el consumidor ocuparía el lugar
  del sondeo y escribiría las mismas instantáneas, y el resto no cambiaría.

## Alternativas descartadas

- **Sondear desde el DAG diario.** Daría una instantánea al día, y una media horaria necesita varias por hora.
- **Un contenedor aparte con un bucle.** Pesa algo menos que una tarea de Airflow, pero no tendría logs, alertas ni
  historial en el mismo sitio que el resto. Una tarea cada 5 minutos sin Spark tarda unos segundos.
- **Agregar al sondear y guardar solo la hora.** Ahorra disco, pero pierde la respuesta original. Con ella, cambiar el
  resumen (otra métrica, otro paso) es recalcular desde bronze, no esperar a acumular datos nuevos.
- **Volver a copiar las instantáneas en el payload de la ventana.** Bronze tendría cada respuesta dos veces. El
  manifiesto solo lleva las claves, y las instantáneas nunca se reescriben con otro contenido.
- **Contar las horas anteriores al primer sondeo como huecos.** El primer día de la fuente saldría con un 60 % de
  huecos que nadie puede arreglar, y la alerta perdería sentido.

## Consecuencias

- **A favor.**
  - Una fuente sin histórico se comporta como las demás a partir de bronze: mismas reglas, mismo DAG diario y la misma
    reconstrucción de silver desde lo guardado.
  - El sondeo no compite por memoria: un proceso de Python sin JVM, de unos 2 segundos y 75 MB, cada 5 minutos.
  - La licencia CC0 permite reutilizar la serie sin condiciones.
- **En contra.**
  - Solo hay serie desde que el poller empezó, y solo mientras el portátil está encendido. Las horas con el equipo
    apagado son huecos reales, y la regla los cuenta.
  - Bronze crece unos 8 MB al día (288 respuestas de estado de unos 25 KB más las de estaciones), unos 3 GB al año. El
    versionado de MinIO no duplica nada, porque cada clave se escribe con el mismo contenido.
  - Silver recibe unas 20.000 filas al día: 106 estaciones × 24 horas × 8 métricas. Es la fuente más voluminosa, unos
    7 millones de filas al año en Postgres.
  - La serie va un día por detrás, como las demás, porque la carga es diaria. El estado de ahora mismo está en bronze,
    pero no llega a la API.

## Cuándo revisarla

- **Si bronze pasa de 10 GB de instantáneas:** comprimirlas (gzip) o compactar cada día ya cargado en un único objeto.
- **Si alguien necesita el estado en minutos y no en días:** cargar las horas cerradas cada hora desde bronze, o pasar a
  un consumidor en streaming. Sería el extra de MQTT, con la misma estructura de bronze.
- **Si Nextbike deja de publicar el GBFS de Palma:** CityBikes sería el plan B, como otro conector con su propio YAML.
