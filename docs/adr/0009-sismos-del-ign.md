# 0009 · Sismos del IGN a través del FDSN de EMSC

- **Estado:** Aceptada. Sustituye a [0008](0008-sismos-de-usgs.md)
- **Fecha:** 2026-10-24

## Contexto

El IGN es la red sísmica nacional y cataloga también los sismos pequeños. Pero su catálogo es un formulario web que
ignora los filtros sin sesión, y su GeoJSON solo cubre los últimos 30 días.

## Decisión

- Leer las localizaciones del IGN desde el servicio FDSN de EMSC, que es estándar y no pide clave. Solo se usan los
  eventos que localizó el IGN (autor `IGN` o `MDD`). Las soluciones de otras agencias se quedan en bronze.
- En el núcleo, la frecuencia `event`: sin regla de huecos, y una ventana sin sismos es una ventana válida.
- En gold, el mart `fct_earthquakes`.

## Alternativas descartadas

- **Hacer scraping del formulario del IGN.** Es frágil y depende de la sesión.
- **Solo el GeoJSON del IGN.** Sin histórico, no hay backfill posible.

## Consecuencias

- **A favor.**
  - Hay histórico desde 2020.
  - La API es estándar.
  - El núcleo gana un concepto general (`frequency: event`) que sirve para cualquier fuente de eventos.
- **En contra.**
  - Se depende de un intermediario, EMSC.
  - La zona es tan tranquila que salen 57 sismos en 2020-2026, incluso ampliando la caja 1° alrededor de la isla.
    El panel de sismos de Grafana dice explícitamente cuándo no hay ninguno en el rango.

## Cuándo revisarla

Si el IGN publica una API con filtros, o si EMSC deja de redistribuir sus localizaciones.
