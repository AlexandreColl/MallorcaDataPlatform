# 0011 · Marcar no es corregir

- **Estado:** Aceptada
- **Fecha:** 2026-10-27

## Contexto

Hay valores que no pueden ser y valores que solo son raros. Una humedad del 140 % es imposible. Un pico de NO₂ de
madrugada es raro, pero puede ser real. Corregir mal un dato borra justo el episodio que interesa, y si el valor
original se pierde no se puede auditar la corrección.

## Decisión

Tres niveles, cada uno en su propia tabla. Ninguno modifica el valor original:

- **Reglas de calidad.** Etiquetan cada fila como `ok`, `suspect` o `missing` y explican la etiqueta en
  `quality_reasons`.
- **Detectores de anomalías.** Escriben en `silver.anomalies`. Hay dos complementarios: un z-score robusto y un
  Isolation Forest multivariante.
- **Correcciones.** Proponen un valor en `silver.corrections`, con el método, la fuente de apoyo, el sesgo y una
  confianza. Llegaron el 2026-11-01.

Gold enseña el valor original y el corregido lado a lado.

## Alternativas descartadas

- **Limpiar en silver** (borrar o sustituir los valores malos). Es irreversible, y no se puede medir.
- **Corregir las anomalías.** Una de cada cinco es un episodio real.

## Consecuencias

- **A favor.** Cada nivel se puede auditar, medir y desactivar sin tocar los demás. Como las anomalías reales no
  vienen etiquetadas, se mide contra una verdad que se conoce:
  - `make evaluate` inyecta fallos conocidos en las series (picos, sensores congelados, derivas, desfases) y mide
    cada detector;
  - `make evaluate-corrections` esconde valores buenos y mide el error de cada método al recuperarlos.

  Esas cifras justifican tener dos detectores y calibrar el sesgo por hora del día. En la presión, el error es de
  14 hPa sin el sesgo y de 0,2 con él.
- **En contra.**
  - Tres tablas y dos valores por fila en gold.
  - Los contaminantes muy locales casi nunca tienen una fuente de apoyo, y sus huecos largos se quedan sin corregir
    a propósito.

## Cuándo revisarla

No se revisa el principio. Lo que puede cambiar son los detectores: el desfase horario se escapa a los dos y queda
pendiente probar uno estacional.
