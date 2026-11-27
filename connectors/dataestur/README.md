# Dataestur (turismo en Baleares)

- **Fuente**: API de datos abiertos de SEGITTUR, <https://www.dataestur.es/API-SEGITTUR-v2> (OpenAPI de 124
  tablas). Cada tabla responde un xlsx con los meses pedidos (`desde (año)`, `desde (mes)`, `hasta`…) y sus
  filtros.
- **Autenticación**: ninguna (la especificación declara una clave, pero no se exige).
- **Datos**: mensuales, del conjunto de Baleares (Mallorca es en torno al 75 %), del aeropuerto de Palma y de los
  cinco puertos de la Autoritat Portuària de Balears (APB).

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
| `cruise_passengers` | PUERTOS | passengers | cruceristas de los puertos de la APB (base y tránsito juntos) |
| `cruise_calls` | PUERTOS | calls | escalas de cruceros en esos puertos |
| `port_passengers` | PUERTOS | passengers | todos los pasajeros de la APB: líneas regulares y cruceros |

Entidades: `baleares` (FRONTUR, EGATUR y EOH), `palma_airport` (AENA) y `apb` (tráfico portuario). `ts` es el día 1 de cada mes a medianoche
local (Europe/Madrid).

## Cómo funciona

1. `extract` pide una hoja por tabla con los meses que cubre la ventana y la guarda **sin tocar** en bronze
   (base64, con su SHA-256). Los filtros (`CCAA de destino: Balears, Illes`, `Provincia: Islas Baleares`,
   `Aeropuerto AENA: P. Mallorca`, `Autoridad portuaria: BALEARES`) van en el YAML, escritos exactamente como en
   el enum de la API. Cada tabla empieza en un año distinto; `first_month` evita pedirle meses que nunca tuvo.
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
- Las cifras son de Baleares, no de Mallorca sola (salvo el aeropuerto). Los cruceristas son de los cinco puertos
  de la APB juntos: Palma es unos dos tercios (68 % en julio de 2024), pero la serie no permite separarla.
- Los cruceristas no distinguen base (empiezan o acaban el crucero aquí) y tránsito (bajan unas horas), y cada
  puerto de escala cuenta a sus pasajeros: un barco que para en Palma y en Maó suma dos veces.
- Histórico: desde 2005 los puertos y el aeropuerto, desde 2012 la ocupación hotelera y desde 2016 FRONTUR y
  EGATUR. `make backfill CONNECTORS=dataestur START=2005-01-01 END=...` lo carga en bloques de un año.

Prueba real (2026-10-28):

- Ejecución por defecto: de septiembre de 2025 a agosto de 2026, 103 filas en 39 s. Falla un hueco por métrica
  hotelera, el de agosto, que aún no está publicado.
- Diez años (septiembre de 2016 a agosto de 2026): 1.069 filas.
  - FRONTUR y EGATUR no tienen abril ni mayo de 2020 (no se publicaron por la pandemia) y la regla de huecos los
    señala.
  - La EOH solo carece del mes de agosto de 2026, que aún no está publicado.
- Agosto de 2026: 2,6 M turistas internacionales (+2,6 % interanual), 4.065 M€ de gasto (1.566 € por turista) y
  4,8 M de pasajeros en el aeropuerto de Palma.

## Cruceristas: lo que enseñaron las pruebas reales (2026-11-27)

Se buscó una serie de cruceristas de Palma y Alcúdia, y solo Dataestur la da en un formato estable:

- **La APB** publica sus estadísticas mensuales como **una imagen PNG por puerto y mes** (portsdebalears.com,
  formulario de año, mes y puerto, de 2007 a hoy). Son las más ricas: por puerto, con base y tránsito, escalas y
  arqueo. Pero leerlas pediría OCR. La ficha de datos.gob.es (`ea0001301-estadisticas-de-trafico-maritimo`) solo
  enlaza a la sede electrónica de la APB, que bloquea a cualquier cliente que no sea un navegador (Cloudflare, 403).
- **Puertos del Estado** publica un xlsx mensual por autoridad portuaria (`CuadrosResumen_AAAA_MM.xlsx`), un mes
  antes que Dataestur, pero en un enlace cuyo número cambia cada mes. Dataestur sirve **la misma serie**
  (`PUERTOS_DL`, filtro `Autoridad portuaria`) en su API estable, desde enero de 2005.
- **Coinciden con la APB**: julio de 2024 da 338.252 cruceristas en Dataestur y 338.244 en la imagen de la APB;
  julio de 2023, 363.423 en las dos. Las escalas difieren en una (82 frente a 83).
- **¿Pasajeros reales o capacidad?** Puertos del Estado los define como los pasajeros de crucero del puerto
  ("incluye inicio, fin de línea y tránsito"), es decir, los que declara la escala. Según la prensa (Última Hora,
  2025), la APB no tiene un recuento en tiempo real y sus cifras salen a menudo de la capacidad de los barcos.
  Ninguna fuente publica el método, así que se toman como **cifra declarada**, no como recuento independiente.
- **Contraste anual**: Ibestat publica una encuesta anual de viajeros de crucero por isla (`000067A_000001`, de 2022
  a 2025, con tripulantes). Es anual, así que no entra en este conector.
- **Escalas previstas**: el visor del puerto (`posidoniaweb.portsdebalears.com`) tiene previsiones, pero es una
  aplicación interna sin licencia ni API documentada. No se usa.
- **Backfill real** (`make backfill CONNECTORS=dataestur START=2005-01-01 END=2026-09-30`): 22 ejecuciones de un año
  en 6 minutos, 2.310 filas. De 2005 a 2011 solo piden el aeropuerto y los puertos, de 2012 a 2015 también los
  hoteles, y desde 2016 las cinco tablas; el aeropuerto y los hoteles ganan así su histórico anterior a 2016. Las
  únicas comprobaciones fallidas son los huecos ya conocidos de FRONTUR y EGATUR en abril y mayo de 2020.
- **Cifras**: 2,58 M cruceristas en 2025; agosto de 2026, 393.270 (+7,4 % interanual) en 122 escalas, unos 3.200
  por escala, frente a 4,8 M pasajeros en el aeropuerto de Palma.
- **Sin cruceros**: de abril de 2020 a mayo de 2021 hay 0 cruceristas (y una sola escala, sin pasajeros, en
  mayo de 2021). Son ceros reales y quedan como tales.

Fixtures en `tests/fixtures/`: las hojas reales de agosto de 2025 a agosto de 2026 y la hoja vacía de un filtro mal
escrito.
