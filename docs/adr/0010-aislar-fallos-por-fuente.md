# 0010 · Una fuente caída no para el resto

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

En una semana normal, alguna API devuelve 5xx, cambia de URL o deja de publicar. Si un fallo de una fuente para el
DAG, ninguna fuente llega a gold.

## Decisión

- Cada conector es una tarea mapeada e independiente.
- Las tareas siguientes se ejecutan de todos modos (`all_done`), y dbt reconstruye gold con lo que sí cargó.
- La siguiente ejecución de una fuente empieza el día después de su última carga correcta (catch-up), así que los
  días perdidos se recuperan solos.
- Cada fallo queda en `ops.ingestion_runs` con su tipo y su mensaje.

## Alternativas descartadas

- **Un DAG por fuente.** Aísla más, pero las anomalías, las correcciones y dbt necesitan un punto común después de la
  ingesta.

## Consecuencias

- **A favor.**
  - El DAG siempre entrega algo.
  - Las alertas de Grafana y el E2E leen los fallos de una tabla.
- **En contra.** Gold puede quedar con una fuente atrasada. Lo dicen la frescura por fuente de dbt y la alerta
  "fuente activa sin ejecución correcta en 36 h".

## Cuándo revisarla

Si las fuentes empiezan a depender unas de otras (una corrección que necesita otra fuente cargada ese mismo día).
Entonces haría falta expresar esas dependencias en el DAG.

## Revisiones

- **2026-11-01.** Al principio, todo fallo se reintentaba. Desde esta revisión se separan dos tipos:
  - **Cortes** (errores de conexión, 5xx, 408 y 429): se reintentan con espera creciente (2, 4 y 8 min).
  - **Fallos que esperar no arregla** (otros 4xx, `SourceNotUpdatedError`): la tarea falla en el acto con
    `AirflowFailException`.

  Con la EEA sin datos, se pasó de unos 14 minutos de reintentos inútiles a fallar en 7 s.
- **2026-11-11.** Una fuente caída deja de contar como fallo ([0022](0022-fuente-caida-no-es-un-fallo.md)):
  - **Cortes** (sin conexión, 5xx): conservan los reintentos y, si la fuente sigue caída en el último, la tarea se
    omite en lugar de fallar. La ejecución queda `unavailable` en `ops.ingestion_runs`.
  - **`SourceNotUpdatedError`** (la fuente aún no ha publicado la ventana): ya no falla en el acto. La tarea se omite
    sin reintentos y la ejecución también queda `unavailable`.
  - **Otros 4xx** (una URL movida, una clave rechazada): siguen fallando sin reintentos, como `failed`.
