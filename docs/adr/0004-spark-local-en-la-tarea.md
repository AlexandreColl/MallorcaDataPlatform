# 0004 · Spark en modo local dentro de la tarea de Airflow

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

Los volúmenes son modestos: cada ejecución diaria trae unas 3.900 filas y silver tiene unos 9 millones. Los
backfills, en cambio, mueven millones de filas (el histórico del Govern son 5 millones de valores). Toda la pila
tiene que caber en unos 8 GB de RAM, en un portátil.

## Decisión

- Cada tarea `ingest` arranca su propio Spark `local[2]`, con 1 GB.
- Como mucho hay dos tareas a la vez (`max_active_tis_per_dagrun=2`).
- `make run-local` ejecuta el mismo pipeline sin Airflow.

## Alternativas descartadas

- **pandas o DuckDB.** Bastarían para la ejecución diaria, pero no cuentan la historia de Spark ni de Delta, y los
  backfills se quedarían sin memoria.
- **Un clúster de Spark en Compose.** Necesita más RAM para hacer el mismo trabajo.

## Consecuencias

- **A favor.**
  - No hay ningún clúster que mantener ni que arrancar aparte.
  - El código es el mismo que correría en un clúster o en Databricks.
- **En contra.** Es el tiempo dominante, con unos 45 s fijos por conector aunque traiga 10 filas:
  - extraer, ~1 s;
  - arrancar la JVM, ~15 s;
  - el primer job, ~11 s;
  - leer el estado de Delta, ~10 s;
  - la compactación, de 8 a 25 s.

## Cuándo revisarla

Hacia 30 fuentes, cuando la ingesta pasa del cuarto de hora. Entonces tocaría un servidor Spark Connect compartido,
que arranca la JVM una sola vez; en la nube, EMR Serverless o Glue. Detalle en
[trade-offs y escalado](../architecture.md#5-trade-offs-costes-y-escalado).
