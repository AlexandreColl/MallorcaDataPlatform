# 0022 · Una fuente caída no es un fallo de la plataforma

- **Estado:** Aceptada
- **Fecha:** 2026-11-11

## Contexto

En noviembre de 2026 la API de Dataestur pasó días devolviendo HTTP 500 en todas sus tablas, con la especificación
OpenAPI sin cambios. El DAG ya aguantaba bien la caída: las otras fuentes cargaban, dbt reconstruía gold y la
ejecución acababa en `success`. Pero la plataforma la contaba como un fallo propio:

- **La tarea de la fuente acababa en rojo** tras unos 15 minutos de reintentos (2, 4 y 8 min), cada día, igual que
  un error de código.
- **`ops.ingestion_runs` la registraba como `failed`**, y con ella la alerta «Ingesta fallida», el panel de fallos de
  Grafana y el KPI de la web. Solo el tipo de excepción del mensaje (`RetryError`, `ConnectTimeout`) permitía
  distinguirla.
- **El E2E ya hacía esa distinción, pero aparte**: una expresión regular sobre el texto del error.

Una fuente caída no se arregla tocando nada: la siguiente ejecución recupera los días con el *catch-up*
([ADR 0003](0003-idempotencia.md)). Mezclarla con los fallos propios esconde los que sí piden trabajo. Esta decisión
cambia cómo [0010](0010-aislar-fallos-por-fuente.md) trataba los cortes, y la 0010 lo recoge en sus revisiones.

## Decisión

- **Un estado más en `ops.ingestion_runs`: `unavailable`.** Lo decide `is_outage` en el núcleo: la fuente no
  responde, responde 5xx después de los reintentos del cliente HTTP, o aún no ha publicado la ventana
  (`SourceNotUpdatedError`). `failed` queda para lo nuestro: un error, un formato que cambió, una clave rechazada.
- **La tarea conserva sus reintentos y, si la fuente sigue caída, se omite en vez de fallar** (`failure_action`:
  `retry`, `skip` o `fail`). Un corte breve se cura solo en el siguiente intento. Una fuente que todavía no ha
  publicado se omite al momento, porque esperar minutos no la hace publicar.
- **Cada cosa avisa por su sitio.**
  - La alerta «Ingesta fallida» solo salta con `failed`.
  - Una caída larga la avisa la regla del SLA: toda ejecución que no cargó cuenta en contra del porcentaje de
    ejecuciones correctas.
  - `gold.source_health` separa `failed_7d` y `unavailable_7d`, y la API y la web los muestran aparte («Fuente
    caída» en naranja).
- **El E2E lee el estado.** `unavailable` es un aviso, como ya lo eran esos errores dentro de `failed`, que se
  mantienen para los registros anteriores.

## Alternativas descartadas

- **Cortocircuito: sin reintentos si la ejecución anterior ya la encontró caída.** Ahorraría los 15 minutos diarios
  de una caída larga, pero cada día es una nueva oportunidad de que vuelva, y los reintentos corren en paralelo a las
  demás fuentes. No compensa el estado extra.
- **Desactivar la fuente a mano mientras dure la caída.** Pide intervenir dos veces y olvidarse de reactivarla
  deja la fuente sin datos aunque haya vuelto.
- **Dejar `failed` y filtrar por el tipo de error en cada consulta.** Es lo que hacía el E2E: cada consumidor
  (alertas, dbt, API, web) tendría que repetir la misma lista de excepciones.

## Consecuencias

- **A favor.**
  - Una caída externa ya no pinta la ejecución de rojo ni dispara la alerta de fallos: el rojo vuelve a significar
    «hay que arreglar algo».
  - La clasificación vive en un solo sitio (`core.connectors`), con tests, y todos los consumidores leen el estado.
- **En contra.**
  - Una tarea omitida es menos visible en Airflow que una fallida. Por eso la caída queda registrada en
    `ops.ingestion_runs` y en Grafana, y si se alarga avisa el SLA.
  - Un 5xx causado por una petición nuestra mal formada contaría como caída. Las APIs que usamos responden 4xx a
    un parámetro mal escrito (o 200 con una hoja vacía, en Dataestur), y el SLA acaba avisando igualmente.

## Cuándo revisarla

- **Si una fuente pasa más días caída que cargando.** Entonces sí compensaría el cortocircuito, o cambiar de fuente.
- **Si aparece un 5xx que resulte ser culpa nuestra**: la clasificación debería mirar también el cuerpo de la
  respuesta.
