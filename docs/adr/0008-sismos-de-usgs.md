# 0008 · Sismos del catálogo de USGS

- **Estado:** Sustituida por [0009](0009-sismos-del-ign.md) el mismo día
- **Fecha:** 2026-10-24

## Contexto

El plan inicial necesitaba una fuente de eventos para probar que el núcleo admite datos sin muestreo regular. El
catálogo de USGS es el estándar mundial, es abierto y su API FDSN es sencilla.

## Decisión

Usar el catálogo de USGS para los sismos de Mallorca.

## Por qué se sustituyó

La prueba real, antes de escribir el conector, devolvió **0 eventos en 12 meses** en la zona. USGS solo cataloga con
detalle fuera de EE. UU. los sismos de magnitud alta, y Mallorca es una zona muy tranquila. Un conector que nunca
trae datos no prueba nada.

## Consecuencias

- Se sustituye por el IGN, la red sísmica nacional ([0009](0009-sismos-del-ign.md)).
- **La lección**, que se aplicó después a todas las fuentes: **probar cada fuente con llamadas reales antes de
  diseñar su conector.** Las notas de cada prueba están en el [ROADMAP](../../ROADMAP.md).
