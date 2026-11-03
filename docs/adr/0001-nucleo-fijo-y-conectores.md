# 0001 · Núcleo fijo y conectores intercambiables

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

Al principio había una docena de fuentes previstas, y llegarían más. Cada una publica en su formato (JSON, CSV,
Parquet, xlsx, ODS, PDF, GTFS, NetCDF), con su frecuencia y su retraso. Si cada fuente tuviera su propia escritura,
su propia calidad y sus propios reintentos, cada una se convertiría en un pipeline distinto que mantener.

## Decisión

- El núcleo (`core/`) solo conoce el contrato `extract()` + `normalize()`.
- Un conector es una carpeta con:
  - su `connector.yaml`, con las métricas, unidades, rangos, frecuencia y retraso;
  - su extractor;
  - sus tests, con respuestas reales grabadas.
- El registro descubre los conectores solo. En dbt, cada fuente es una vista de staging de una línea
  (`{{ staging_observations('ign') }}`).
- Todas las fuentes van a un esquema común largo: una fila por valor (`source, entity, metric, ts, value, unit,
  quality, lat, lon`).
- Si una fuente necesita algo nuevo, el núcleo gana un concepto general y no un caso especial.

## Alternativas descartadas

- **Un pipeline por fuente.** Repite la escritura, la calidad y los reintentos en cada fuente.
- **Herramientas de ingesta genéricas (Airbyte, dlt).** No cubren GTFS, THREDDS ni PDF, y esconden justo la parte que
  el proyecto quiere enseñar.

## Consecuencias

- **A favor.**
  - Las once fuentes que llegaron después de Open-Meteo entraron en el mismo DAG y el mismo pipeline, sin ninguno
    propio.
  - Cuando una fuente pidió algo nuevo, el núcleo ganó un concepto general: `frequency: event` para los sismos,
    `1mo` para el turismo y `lag_days` para AEMET.
- **En contra.**
  - El esquema largo obliga a pivotar en los marts.
  - Los datos que no son series se resumen en una serie (autobuses por parada y día) o se quedan fuera
    (geometrías, horarios completos).

## Cuándo revisarla

Cuando haga falta guardar tipos que no son números (texto, geometría). Entonces habría tablas anchas por dominio en
silver, y el esquema largo quedaría solo para las series.
