# 0016 · Silver en Delta Lake

- **Estado:** Aceptada. Sustituye a [0005](0005-silver-en-parquet.md)
- **Fecha:** 2026-11-02

## Contexto

El lake en Parquet, particionado por fuente y día ([0005](0005-silver-en-parquet.md)), tenía tres problemas:

- había llegado a 16.973 particiones de unos 17 KB, repartidas en 67.000 ficheros;
- sobrescribir no dejaba historial;
- cada relanzamiento reescribía el día entero.

## Decisión

- Delta Lake 4.4 sobre MinIO, con una partición por fuente.
- `MERGE` por la clave, solo con las filas nuevas o cambiadas.
- Change Data Feed activado.
- Compactación automática tras cada escritura. `OPTIMIZE … ZORDER BY (ts)` y `VACUUM` corren con
  `make silver-maintain`.
- El lake existente se convirtió en su sitio (`CONVERT TO DELTA`) y se reescribió una vez.
- Dos conectores escriben a la vez y Delta en S3 no tiene un "escribir si no existe" atómico desde Spark. Por eso un
  *advisory lock* de Postgres (clave 7303) serializa los commits. Es el papel que en AWS haría el LogStore de
  DynamoDB.

## Alternativas descartadas

- **Iceberg.** Todavía no tiene runtime para Spark 4.2.
- **Partir también por día.** Deja ficheros diminutos, y `OPTIMIZE` tardaba 25 min en lugar de 2,7.
- **El paquete de Python `delta-spark`.** Fija una versión de PySpark anterior a la del proyecto, así que se usan
  solo los jars de Delta.

## Consecuencias

- **A favor.**
  - El lake pasó de 67.000 ficheros a 12.
  - Cada carga es una versión, con *time travel* y la lista de filas que cambiaron (`make silver-changes`).
  - Una ejecución sin cambios no crea ninguna versión.
  - Athena lee la tabla a través de Glue, sin crawlers.
- **En contra.**
  - Hay que compactar.
  - El lock deja un solo escritor a la vez, y la compactación (de 8 a 25 s) ocurre dentro del lock.

## Cuándo revisarla

Con más de dos escritores a la vez. Entonces tocaría:

- compactar fuera del lock, con un `OPTIMIZE` periódico;
- en AWS, el LogStore de DynamoDB;
- revisar Iceberg cuando tenga runtime para la versión de Spark en uso.
