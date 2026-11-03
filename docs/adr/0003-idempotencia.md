# 0003 · Idempotencia en todas las capas

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

Las ventanas ya cargadas se vuelven a ejecutar por varios motivos: los reintentos, los backfills, el catch-up de
días perdidos ([0010](0010-aislar-fallos-por-fuente.md)) y las fuentes que revisan sus datos. Si relanzar duplica
filas o deja datos a medias, cada relanzamiento hay que pensarlo antes.

## Decisión

- **Ventanas.** Son siempre días completos, así que la misma petición da siempre la misma clave de bronze.
- **Silver.** Se escribe por la clave (fuente, entidad, métrica, instante):
  - en el lake, con `MERGE` ([0016](0016-silver-en-delta.md));
  - en Postgres, con `INSERT … ON CONFLICT … DO UPDATE … WHERE (…) IS DISTINCT FROM (…)`.

  Las filas que no cambian no se reescriben y conservan su `updated_at`.
- **Anomalías y correcciones.** Se recalculan los últimos 14 días y se reemplazan en una sola transacción.
- **Gold.** dbt es incremental y usa como marca de agua el `updated_at` de silver.

## Alternativas descartadas

- **Sobrescribir particiones.** Es idempotente, pero reescribe ficheros enteros y deja una versión nueva en cada
  ejecución aunque no cambie nada.
- **Solo insertar y deduplicar al leer.** La tabla crece con cada relanzamiento, y todas las lecturas pagan esa
  deduplicación.

## Consecuencias

- **A favor.**
  - Relanzar algo no hay que pensarlo dos veces.
  - El E2E del CI ejecuta el DAG dos veces y falla si cambia el número de filas de silver.
  - Relanzar una ventana sin cambios no crea ninguna versión de Delta.
  - `tests/test_warehouse.py` comprueba el upsert contra un Postgres real.
- **En contra.**
  - Antes del `MERGE` hace falta un *anti-join* contra la tabla. Las estadísticas de los ficheros lo acotan por
    fuente y por días.
  - Recalcular 14 días repite trabajo todos los días (unos 57 s).

## Cuándo revisarla

La idempotencia no se revisa. Lo que puede cambiar es el recálculo: con muchas más series, convendría recalcular
solo las que cambiaron, que el Change Data Feed de Delta ya indica.
