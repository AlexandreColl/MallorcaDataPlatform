# 0005 · Silver en Parquet particionado por fuente y día

- **Estado:** Sustituida por [0016](0016-silver-en-delta.md) el 2026-11-02
- **Fecha:** 2026-10-24

## Contexto

En la v0.1 había una sola fuente y la ejecución diaria traía pocas filas. Hacía falta un lake en MinIO que fuera
estándar, que Spark escribiera sin jars extra y que fuera idempotente al relanzar un día.

## Decisión

- Silver en Parquet, en `s3a://silver/observations`, particionado por `source` y `date`.
- Escritura con `mode("overwrite")` y sobrescritura dinámica de particiones: relanzar un día reemplaza solo ese día.

## Alternativas descartadas

- **Delta o Iceberg desde el principio.** Añadían jars y conceptos (log de transacciones, compactación) antes de que
  hicieran falta.

## Consecuencias

- **A favor.** Era sencillo, estándar e idempotente por día.
- **En contra.** Con once fuentes y backfills de décadas:
  - el lake llegó a **16.973 particiones de unos 17 KB, repartidas en 67.000 ficheros**;
  - sobrescribir no dejaba historial, así que no se podía saber qué había cambiado ni volver atrás;
  - cada relanzamiento reescribía el día entero aunque no cambiara nada.

## Por qué se sustituyó

Esas tres consecuencias pesaron más que la sencillez. [0016](0016-silver-en-delta.md) lleva silver a Delta Lake,
con una partición por fuente: el lake pasó de 67.000 ficheros a 12, ganó historial y *time travel*, y una ejecución
sin cambios no escribe nada. La tabla se convirtió en su sitio (`CONVERT TO DELTA`), sin volver a descargar nada de
las fuentes.

**La lección:** partir por día parecía natural, pero con datos pequeños deja ficheros diminutos. La partición tiene
que salir del volumen, no de la forma de las consultas.
