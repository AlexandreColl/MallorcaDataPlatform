# 0006 · Postgres como warehouse y dbt para gold

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

Grafana y la API necesitan respuestas en milisegundos sobre tablas pequeñas. La plataforma no tiene presupuesto, y
la RAM de la pila ya está repartida entre Airflow, Spark y MinIO.

## Decisión

- PostgreSQL es el warehouse y también guarda el estado operativo (`ops.*`, `quality.*`).
- dbt construye gold.
- Los dos hechos grandes son incrementales y usan como marca de agua el `updated_at` de silver.
- Los marts que consumen la API y Grafana tienen contrato (`contract: enforced`).

## Alternativas descartadas

- **Athena o Trino para todo.** En local hacen falta otro servicio y más RAM, y su latencia no sirve para
  dashboards.
- **DuckDB.** Es muy rápido, pero no admite varios escritores a la vez ni acceso por red para Grafana.

## Consecuencias

- **A favor.**
  - Un solo servicio sirve las consultas, recibe dbt y guarda el estado.
  - Con los incrementales, `dbt build` tarda unos 2 minutos con 9 millones de filas en silver.
  - Los contratos son la frontera con la API: si una columna cambia, el build falla.
- **En contra.** El almacenamiento es por filas, no columnar: gold (3,3 GB) ocupa más que silver (2,6 GB).

## Cuándo revisarla

Cuando gold pase de unos 100 millones de filas o las consultas de Grafana tarden segundos.

1. Primero, particionar `fct_observations` por mes.
2. Después, un motor columnar con el mismo dbt (`dbt-athena`, BigQuery o Snowflake), y Postgres solo para servir
   marts pequeños.

## Revisiones

- **2026-10-27.** Gold deja de ser una carpeta plana y pasa a tres capas: staging → intermediate → marts por
  dominio. Llegan con ello los hechos incrementales, la frescura por fuente, un snapshot, los contratos y tests
  unitarios de dbt.
