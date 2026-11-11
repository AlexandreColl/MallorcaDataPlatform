# Registro de decisiones de arquitectura (ADR)

Cada fichero recoge una decisión: el contexto en que se tomó, lo que se decidió, las alternativas que se
descartaron, lo que cuesta y cuándo habría que revisarla. Una decisión no se borra nunca. Cuando otra la sustituye,
cambia su estado y enlaza a la nueva, así que el registro también cuenta cómo ha evolucionado la plataforma.

La vista de conjunto (diagramas, atributos de calidad, costes y escalado) está en el
[caso de arquitectura](../architecture.md).

## Estados

| Estado | Significado |
|---|---|
| Aceptada | En vigor |
| Sustituida | Otra ADR la reemplaza; se enlaza a ella |
| Rechazada | Se estudió y no se adoptó; se guarda el porqué |

Una ADR aceptada que cambia en parte, sin cambiar de fondo, lleva una sección **Revisiones** con la fecha y el
cambio.

## Índice

| ADR | Decisión | Estado | Fecha |
|---|---|---|---|
| [0001](0001-nucleo-fijo-y-conectores.md) | Núcleo fijo y conectores intercambiables | Aceptada | 2026-10-24 |
| [0002](0002-medallion.md) | Medallion: bronze crudo, silver común, gold con dbt | Aceptada | 2026-10-24 |
| [0003](0003-idempotencia.md) | Idempotencia en todas las capas | Aceptada | 2026-10-24 |
| [0004](0004-spark-local-en-la-tarea.md) | Spark en modo local dentro de la tarea de Airflow | Aceptada | 2026-10-24 |
| [0005](0005-silver-en-parquet.md) | Silver en Parquet particionado por fuente y día | Sustituida por [0016](0016-silver-en-delta.md) | 2026-10-24 |
| [0006](0006-postgres-y-dbt.md) | Postgres como warehouse y dbt para gold | Aceptada | 2026-10-24 |
| [0007](0007-calidad-de-ingenieria.md) | Calidad de ingeniería y entrega | Aceptada | 2026-10-24 |
| [0008](0008-sismos-de-usgs.md) | Sismos del catálogo de USGS | Sustituida por [0009](0009-sismos-del-ign.md) | 2026-10-24 |
| [0009](0009-sismos-del-ign.md) | Sismos del IGN a través del FDSN de EMSC | Aceptada | 2026-10-24 |
| [0010](0010-aislar-fallos-por-fuente.md) | Una fuente caída no para el resto | Aceptada | 2026-10-24 |
| [0011](0011-marcar-no-es-corregir.md) | Marcar no es corregir | Aceptada | 2026-10-27 |
| [0012](0012-calidad-del-aire-de-openaq.md) | Calidad del aire desde OpenAQ | Rechazada | 2026-10-29 |
| [0013](0013-calidad-del-aire-de-la-eea.md) | Calidad del aire del servicio de descarga de la EEA | Aceptada | 2026-10-29 |
| [0014](0014-servir-gold.md) | Servir gold: Grafana como código y una API pequeña | Aceptada | 2026-10-29 |
| [0015](0015-local-primero-nube-descrita.md) | Local primero, nube descrita con Terraform | Aceptada | 2026-10-30 |
| [0016](0016-silver-en-delta.md) | Silver en Delta Lake | Aceptada | 2026-11-02 |
| [0017](0017-observabilidad-y-linaje.md) | Observabilidad y linaje | Aceptada | 2026-11-02 |
| [0018](0018-sin-cache-de-extraccion.md) | Sin caché aparte (Redis) para la extracción | Aceptada | 2026-11-03 |
| [0019](0019-frontal-web-sobre-la-api.md) | Un frontal web propio que solo lee la API | Aceptada | 2026-11-05 |
| [0020](0020-gobierno-del-dato-en-el-catalogo-de-fuentes.md) | El gobierno del dato vive en el catálogo de fuentes, con un SLA por fuente | Aceptada | 2026-11-09 |
| [0021](0021-solo-los-dias-que-faltan.md) | Un DAG diario que solo descarga los días que faltan | Aceptada | 2026-11-10 |
| [0022](0022-fuente-caida-no-es-un-fallo.md) | Una fuente caída no es un fallo de la plataforma | Aceptada | 2026-11-11 |

Las fechas son las del commit que llevó la decisión a `develop`. Las ADR se escribieron a la vez el 3 de
noviembre de 2026, a partir del historial y de las notas de cada PR.

## Cómo añadir una

1. Copia [template.md](template.md) como `NNNN-titulo-corto.md`, con el siguiente número libre.
2. Rellénala en el mismo PR que lleva el cambio y añádela al índice.
3. Si sustituye a otra, cambia el estado de la antigua y enlaza a la nueva en las dos.
