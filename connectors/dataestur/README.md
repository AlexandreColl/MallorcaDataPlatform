# Dataestur (turismo en Baleares)

- **Fuente**: API de datos abiertos de SEGITTUR, <https://www.dataestur.es/API-SEGITTUR-v2> (OpenAPI de 124
  tablas). Cada tabla responde un xlsx con los meses pedidos (`desde (año)`, `desde (mes)`, `hasta`…) y sus
  filtros.
- **Autenticación**: ninguna (la especificación declara una clave, pero no se exige).
- **Datos**: mensuales, del conjunto de Baleares (Mallorca es en torno al 75 %) y del aeropuerto de Palma.

| Métrica | Tabla | Unidad | Qué es |
|---|---|---|---|
| `international_tourists` | FRONTUR | people | turistas internacionales llegados (sin excursionistas), suma de los países de residencia |
| `international_tourist_spending` | EGATUR | EUR | gasto total de los turistas internacionales |
| `international_tourist_nights` | EGATUR | nights | pernoctaciones de esos turistas |
| `hotel_guests` | EOH | people | viajeros alojados en hoteles (residentes en España y en el extranjero) |
| `hotel_nights` | EOH | nights | pernoctaciones hoteleras |
| `hotel_bed_occupancy` | EOH | % | grado de ocupación por plazas |
| `hotels_open` | EOH | establishments | hoteles abiertos estimados (en enero, unos 150; en verano, 1.370) |
| `hotel_staff` | EOH | people | personal empleado en hoteles |
| `airport_passengers` | AENA | passengers | pasajeros del aeropuerto de Palma |

Entidades: `baleares` (FRONTUR, EGATUR y EOH) y `palma_airport` (AENA). `ts` es el día 1 de cada mes a medianoche
local (Europe/Madrid).

## Cómo funciona

1. `extract` pide una hoja por tabla con los meses que cubre la ventana y la guarda **sin tocar** en bronze
   (base64, con su SHA-256). Los filtros (`CCAA de destino: Balears, Illes`, `Provincia: Islas Baleares`,
   `Aeropuerto AENA: P. Mallorca`) van en el YAML, escritos exactamente como en el enum de la API.
2. `normalize` lee el xlsx con la librería estándar (un xlsx es un zip de XML: la imagen no necesita openpyxl),
   se queda con las filas de `where` (FRONTUR: `Turista`; EOH: la fila `Total`) y convierte cada columna mapeada
   en un valor por mes: sumando países de residencia con `sum_rows` o, sin él, con una sola fila por mes (si hay
   más, falla en lugar de sumar porcentajes).
3. Solo se cargan los meses cuyo día 1 cae dentro de la ventana.

Una frecuencia mensual pide dos cosas al núcleo, que ahora existen para cualquier conector:

- `frequency: 1mo`: la regla de huecos cuenta meses naturales, no la duración de la ventana entre 30 días.
- `min_days: 365`: la ejecución diaria del DAG (`days: 1`) pediría un mes aún sin publicar; con `min_days` cada
  ejecución relee el último año, lo que además recoge las revisiones de los meses ya publicados. Las filas que no
  cambian no se reescriben (el merge solo actualiza lo distinto).

`lag_days: 62` termina la ventana unos dos meses atrás, que es lo que tardan FRONTUR, EGATUR y AENA. La ocupación
hotelera sale un mes más tarde, así que su último mes falta y la regla de huecos lo cuenta hasta que se publica.

## Limitaciones

- Un filtro mal escrito no da error: la API responde 200 con la hoja vacía. Como la ventana siempre cubre meses
  publicados, una hoja vacía se trata como error.
- Las cifras son de Baleares, no de Mallorca sola (salvo el aeropuerto).
- Histórico: `--days 3650` carga diez años en un minuto (`max_days: 3660`).

Prueba real (2026-10-28):

- Ejecución por defecto: de septiembre de 2025 a agosto de 2026, 103 filas en 39 s. Falla un hueco por métrica
  hotelera, el de agosto, que aún no está publicado.
- Diez años (septiembre de 2016 a agosto de 2026): 1.069 filas.
  - FRONTUR y EGATUR no tienen abril ni mayo de 2020 (no se publicaron por la pandemia) y la regla de huecos los
    señala.
  - La EOH solo carece del mes de agosto de 2026, que aún no está publicado.
- Agosto de 2026: 2,6 M turistas internacionales (+2,6 % interanual), 4.065 M€ de gasto (1.566 € por turista) y
  4,8 M de pasajeros en el aeropuerto de Palma.

Fixtures en `tests/fixtures/`: las hojas reales de agosto de 2025 a agosto de 2026 y la hoja vacía de un filtro mal
escrito.
