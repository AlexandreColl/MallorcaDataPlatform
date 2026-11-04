# 0017 · Observabilidad y linaje

- **Estado:** Aceptada
- **Fecha:** 2026-11-02

## Contexto

Con doce fuentes poco fiables, hay que saber sin mirar los logs qué falló, qué está atrasado y qué regla de calidad
se ha puesto en rojo. Y ante un dato raro en gold, hay que poder seguirlo hasta la tarea y la fuente que lo
escribieron.

## Decisión

- **Estado de la ingesta.** Cada ejecución deja su estado y su error en `ops.ingestion_runs`.
- **Calidad.** Los resultados van a `quality.check_results`. Cada fila de silver lleva su `run_id`.
- **Alertas** (desde el 2026-10-30).
  - Tres alertas de Grafana leen esas tablas:
    - una ingesta fallida;
    - una fuente sin ejecución correcta en 36 h;
    - una regla que pasa de verde a rojo.
  - Si hay token en el `.env`, avisan por Telegram.
- **Linaje** (desde el 2026-11-02), con OpenLineage y opcional.
  - Las tareas declaran como *assets* los datos que leen y escriben.
  - dbt corre como `dbt-ol`, con linaje por columna.
  - Marquez lo dibuja todo como un solo grafo, de la ingesta a gold.

## Alternativas descartadas

- **La integración de OpenLineage con Spark.** Las filas salen de Python, no de una lectura de Spark, así que solo
  repetiría lo que ya declara la tarea `ingest`.
- **Alertas desde Airflow.** No verían una regla de calidad en rojo ni una fuente que deja de publicar sin fallar.

## Consecuencias

- **A favor.**
  - Las alertas avisan aunque dbt no corra.
  - Las tablas de Airflow y las de dbt usan el mismo nombre de dataset, así que el grafo de linaje no se corta.
  - Sin `OPENLINEAGE_URL` no se envía nada y la pila no crece.
- **En contra.** Marquez es otro servicio (perfil `lineage` de Compose).

## Cuándo revisarla

Si aparecen SLAs formales por fuente (está en la fase 7 del ROADMAP). Entonces las alertas pasarían de umbrales
fijos, como las 36 h, a la frescura que se haya acordado con cada fuente.
