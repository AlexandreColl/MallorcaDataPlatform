# 0021 · Un DAG diario que solo descarga los días que faltan

- **Estado:** Aceptada
- **Fecha:** 2026-11-10

## Contexto

La plataforma corre en un portátil que se apaga cada noche. Los datos sobreviven a los reinicios, porque Postgres,
MinIO, Grafana y los logs viven en volúmenes con nombre de Docker. Pero cada arranque costaba trabajo:

- **El DAG no tenía programación** (`schedule=None`). Tras encender el PC nadie lo lanzaba, y las fuentes se quedaban
  atrasadas hasta lanzarlo a mano.
- **Una ejecución pedía siempre su ventana entera.** `make run DAYS=30` volvía a descargar 30 días aunque 29 ya
  estuvieran cargados. El *catch-up* ([ADR 0003](0003-idempotencia.md)) solo alarga la ventana
  hacia atrás; nunca la acorta.

El [ADR 0018](0018-sin-cache-de-extraccion.md) ya apuntaba la salida: antes que una caché, no volver a pedir lo que
ya está.

## Decisión

- **`only_missing`**, activo por defecto en el DAG y en `make run`. Antes de llamar a la fuente, cada conector
  pregunta a `ops.ingestion_runs` qué días de su ventana no ha cubierto ninguna carga correcta (`missing_days`):
  - **Si no falta ninguno,** no descarga nada, no arranca Spark y no registra ejecución.
  - **Si faltan,** la ventana empieza en el primer día que falta. Un hueco en medio se descarga junto con lo que le
    sigue.
  - **Las fuentes que releen a propósito para recoger revisiones** (`min_days > 1`: las mensuales, el padrón y el IPH)
    conservan su ventana entera en cuanto falta un día. Como su último día cambia cada día, releen una vez al día,
    pero no en cada reinicio.
- **El DAG corre cada día** (`MDP_SCHEDULE`, por defecto `@daily`) y sin `catchup`. Si el PC estaba apagado, el
  scheduler lanza la ejecución pendiente en cuanto Airflow vuelve, una sola vez, y cada conector recupera sus días con
  `only_missing` y su *catch-up*.
- `ONLY_MISSING=false` (o `"only_missing": false` en el conf) vuelve a descargar la ventana entera. La E2E lo usa: su
  segunda ejecución debe recargar la misma ventana para demostrar que no duplica nada. También apaga la programación
  (`MDP_SCHEDULE=none`), porque lanza sus propias ejecuciones.

## Alternativas descartadas

- **Leer de bronze lo que ya se descargó.** Ahorra la petición, pero no el resto: Spark, el MERGE de Delta y el upsert
  de Postgres. Saltar la ejecución entera lo ahorra todo. Además, una ventana releída de bronze no recogería las
  revisiones de la fuente, que es justo por lo que algunas releen.
- **Un servicio de arranque que lance el DAG al levantar el stack.** Duplicaría lo que Airflow ya hace con una
  programación sin `catchup`, y un `docker compose up` repetido lo lanzaría varias veces.
- **`catchup=True`.** Lanzaría una ejecución por cada día que el PC estuvo apagado. Basta una, porque los conectores
  saben qué les falta.

## Consecuencias

- **A favor.**
  - Un reinicio solo trae lo que falta: medido con Open-Meteo, una ventana de 3 días con 2 ya cargados descarga uno, y
    repetirla no descarga nada ni arranca Spark.
  - Los datos se mantienen al día solos mientras el PC está encendido, y los SLA de
    [ADR 0020](0020-gobierno-del-dato-en-el-catalogo-de-fuentes.md) se cumplen sin intervenir.
- **En contra.**
  - Lo que decide "cargado" es el registro de ejecuciones, no los datos. Si se borran filas de silver a mano, hay que
    recargar con `ONLY_MISSING=false`.
  - El *catch-up* sigue limitado a `catch_up_days`, que por defecto es el `max_days` de cada conector (92 días en
    Open-Meteo, REData o la EEA; 366 en AEMET): lo que su API sirve de una vez. Desde la v0.16.0, `recover_days`
    recupera un hueco más largo, en ejecuciones extra, en las fuentes cuya API guarda el histórico (AEMET y REData).
    Más allá, los días se cargan con `make backfill`.
  - Una ejecución saltada no deja fila en `ops.ingestion_runs`. Solo ocurre si una carga correcta reciente ya cubrió
    el último día, así que la alerta de 36 h sin carga correcta no salta por ello.

## Cuándo revisarla

- **Si el stack pasa a un servidor siempre encendido.** La programación diaria sigue valiendo, y `only_missing` solo
  evitaría las relecturas manuales.
- **Si alguna fuente necesita relecturas largas por revisiones.** Subir su `min_days` basta, sin tocar esta lógica.
