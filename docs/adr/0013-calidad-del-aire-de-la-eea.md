# 0013 · Calidad del aire del servicio de descarga de la EEA

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Las estaciones oficiales de Mallorca son de la red del Govern, y el Govern las reporta a la Agencia Europea de Medio
Ambiente (EEA). La EEA las publica en un servicio de descarga que no pide clave. OpenAQ no sirve como intermediario
([0012](0012-calidad-del-aire-de-openaq.md)).

## Decisión

- Leer de la EEA, que da una búsqueda en JSON y un Parquet por estación y contaminante.
- Los datos son horarios y llegan unas dos horas por detrás del tiempo real.
- Hay 9 estaciones oficiales de Mallorca, con las coordenadas de OpenAQ.
- El histórico del Govern (2002-2021) llega por un conector aparte.
- Desde el 2026-11-01 se leen también los datos verificados de los años anteriores.

## Alternativas descartadas

- **OpenAQ o aqicn.** Ver [0012](0012-calidad-del-aire-de-openaq.md).
- **El portal del Govern para todo.** Su histórico acaba en 2021.

## Consecuencias

- **A favor.**
  - Es la fuente oficial, con todas las horas, y en Parquet.
  - Permite el mart `fct_air_quality_model_bias_daily`, que compara el modelo CAMS con la estación.
- **En contra.** El feed a veces se queda días sin publicar. El conector lo trata como un corte de la fuente
  (`SourceNotUpdatedError`) y no lo reintenta ([0010](0010-aislar-fallos-por-fuente.md)).

## Cuándo revisarla

Si la EEA cambia o retira el servicio de descarga. El E2E semanal lo detectaría
([0007](0007-calidad-de-ingenieria.md)).
