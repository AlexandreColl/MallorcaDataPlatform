# Ibestat (presión humana)

- **Fuente**: Indicador de Presión Humana (IPH) del Ibestat, conjunto `000011A_000002` (*Indicador de Presión
  Humana (IPH). Illes Balears, islas y día*), desde su API eDatos:
  `https://ibestat.es/edatos/apis/statistical-resources/v1.0/datasets/IBESTAT/000011A_000002/~latest.json`.
  - `dim=TERRITORIO:ES532:TIME_PERIOD:2026-08-01|2026-08-02|…` pide solo Mallorca y los días de la ventana.
  - `fields=-metadata` quita los metadatos del conjunto: un año de Mallorca ocupa unos 20 KB en lugar de los 3 MB
    del cubo entero.
- **Autenticación**: ninguna.
- **Datos**: las personas presentes en Mallorca cada día. Son los residentes empadronados, más los visitantes que
  llegan por puerto o aeropuerto, menos los residentes que están fuera. La serie empieza el 1 de enero de 1997.

| Métrica | Medida | Unidad |
|---|---|---|
| `human_pressure` | `IPH` | `people` |

La `entity` es `mallorca`, con el centro de la isla como coordenadas. El conjunto también trae el total balear
(`ES53`), Menorca, Eivissa y Formentera. El YAML lista solo Mallorca, y el conector se queda con los territorios
cuyo centro cae dentro de la región.

## Un cubo plano

eDatos devuelve un cubo con tres partes:

- **Las dimensiones**: día, territorio y medida, con el código y la posición de cada valor.
- **Las observaciones**: una sola cadena separada por `" | "`, en orden de filas.
- **El estado de cada observación** (`ESTADO_OBSERVACION`), en el mismo orden. Es un código SDMX:

| Estado | Significado | Calidad |
|---|---|---|
| `A` | Valor normal | `ok` |
| `P` | Provisional | `ok` |
| `E` | Estimado (los meses recientes) | `ok` |
| `O` | Ausente | `missing` |
| (en blanco) | Día aún no publicado | no se guarda |

Un día con el valor y el estado en blanco todavía no está publicado. No se guarda como ausente: si cae dentro de la
ventana, lo marca la regla de huecos.

## Ventana

- **`lag_days: 95`**: el Ibestat publica un mes a principios del tercer mes siguiente. Agosto salió el 4 de
  noviembre y septiembre sale el 2 de diciembre, así que el último día publicado puede tener unos 92 días. Como la
  ventana acaba 95 días antes de ayer, todos sus días están normalmente publicados.
- **`min_days: 120`**: cada ejecución relee los últimos 120 días. Los días recientes son estimaciones (`E`) y se
  revisan en las publicaciones siguientes.
- **`max_days: 11000`**: todo el histórico desde 1997 cabe en un único backfill. Los días van en la URL, así que la
  ventana se trocea en peticiones de un año como máximo (`max_days_per_request`).

## Gold

`fct_human_pressure_daily` compara cada día con los empadronados en Mallorca según el padrón del INE de ese año, o
el último anterior si el de ese año aún no ha salido. Da la diferencia y el cociente entre presentes y residentes.
La API lo sirve en `/v1/population/pressure`, y la web lo dibuja en *Movilidad*: los tres últimos años superpuestos,
frente a los empadronados.

## Lo que enseñaron las pruebas reales (2026-11-07)

- **El backfill de 1997 al 31 de agosto de 2026 son 10.835 días**, en 30 peticiones. No falla ninguna regla de
  calidad.
- **Agosto de 2026 es el mes con más gente de la serie**. El 11 de agosto hubo 1.517.631 personas, 1,58 por cada
  uno de los 960.270 empadronados. La media de 2026 hasta agosto es de 1,24 millones.
- **En 1997 la isla tenía unas 612.000 personas a principios de enero**, frente a 609.150 empadronados.
- **Sin el filtro de dimensiones**, la respuesta es el cubo entero de las seis zonas desde 1997 (3,8 MB). Con el
  filtro y sin metadatos, una ventana de 120 días ocupa 7,5 KB.
