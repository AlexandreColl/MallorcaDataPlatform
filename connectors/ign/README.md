# IGN (sismos)

- **Fuente**: localizaciones del Instituto Geográfico Nacional publicadas en el servicio FDSN de EMSC:
  <https://www.seismicportal.eu/fdsnws/event/1/query> (formato `text`).
- **Autenticación**: ninguna.
- **Datos**: sismos localizados por el IGN (`Author` = `IGN`, o `MDD` en eventos antiguos) en la caja de la región
  ampliada `margin_deg` (1°) para cubrir el mar que rodea la isla.

| Columna FDSN | Métrica | Unidad | Rango válido |
|---|---|---|---|
| `Magnitude` | `magnitude` | M (magnitud local, `ml`) | -2 a 10 |
| `Depth/km` | `depth_km` | km | -5 a 700 |

Cada sismo es una `entity` (su `EventID`) con el epicentro como `lat`/`lon` y la hora de origen como `ts`.

## Por qué FDSN y no la web del IGN

Las pruebas reales (2026-10-24) descartaron las dos vías propias del IGN:

- El **catálogo** es un formulario de un portal web: sin sesión ignora los filtros y devuelve el catálogo
  completo de España en HTML, paginado de 50 en 50.
- El **feed GeoJSON** (`terremotos.js`) cubre solo los últimos 3, 10 y 30 días de toda España: no sirve para
  histórico y en esos 30 días no tenía ningún sismo en Baleares.

FDSN es el estándar internacional de servicios sismológicos: admite rango de fechas y caja geográfica, y
contesta `204 No Content` cuando no hay eventos. EMSC republica las localizaciones del IGN, así que los valores
son los del IGN. Las soluciones de otras agencias (p. ej. `EMSC`) se guardan en bronze y no pasan a silver.

## Una fuente de eventos

Mallorca es una zona tranquila: en la caja ampliada el IGN localizó 57 sismos entre 2020 y 2026 (unos 9 al año).
Por eso el dataset declara `frequency: event`:

- **Sin regla de huecos**: un sismo en un día no son 23 horas vacías.
- **Ventanas vacías válidas**: con `days: 1` lo normal es no tener eventos. La respuesta vacía se guarda en
  bronze y la ejecución termina correctamente con 0 filas (el resto de fuentes fallan si no traen datos).
- Las reglas de fila (rango, duplicados) sí se aplican.

En gold, `fct_earthquakes` da una fila por sismo con su distancia a Palma. Si una agencia revisa la hora de
origen de un evento, silver guarda las dos versiones y gold usa la última ingerida.

Prueba real (2026-10-24, 2.500 días): 57 sismos desde 2020, magnitud máxima 3,0, el más cercano a 8,9 km de
Palma (bahía de Palma, 15/05/2025). Fixture en `tests/fixtures/events_2025q3.txt` (julio-septiembre de 2025:
5 sismos del IGN y 1 de EMSC).
