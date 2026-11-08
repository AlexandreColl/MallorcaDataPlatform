# EMT Palma (autobús urbano)

- **Fuente**: GTFS estático de EMT Palma, publicado en su GitHub:
  <https://github.com/emtpalma/Open-Data/raw/master/lineas-paradas-horarios-gtfs.zip> (~0,5 MB). También está en
  el Punto de Acceso Nacional (NAP), pero allí exige registro.
- **Autenticación**: ninguna.
- **Datos**: 42 líneas y 875 paradas, con el horario expresado por frecuencias.

| Métrica | Unidad | Qué es |
|---|---|---|
| `scheduled_departures` | buses | autobuses programados que pasan por la parada ese día |
| `lines_served` | lines | líneas distintas que pasan por la parada ese día |
| `scheduled_trips` | trips | salidas de la línea ese día (entidad `route_<route_id>`, sin coordenadas) |

Cada parada es una `entity` (`stop_<stop_id>`) con su posición; `ts` es la medianoche local (Europe/Madrid) del día
de servicio.

## Líneas y recorridos

Cada línea es otra `entity` (`route_<route_id>`) con su serie de salidas por día. `describe` le pone nombre
(`1 · Portopí - Sindicat`), y `routes` guarda su recorrido en `silver.routes`:

- **Qué forma se guarda**: en cada sentido, la forma de `shapes.txt` que siguen más viajes.
- **Simplificación**: Douglas-Peucker a unos 10 m. Los 48.000 puntos de EMT quedan en 5.000, unos 50 kB.
- **Color**: el de la línea (`route_color`).

Cada ejecución sustituye las líneas de la fuente, así que una línea que desaparece del feed desaparece de la tabla.
La web dibuja los recorridos en *Movilidad*, con un grosor que crece con las salidas.

## Cómo funciona

1. `extract` descarga el zip y lo guarda **sin tocar** en bronze (base64, con su SHA-256 y tamaño en la petición).
2. `normalize` decide qué servicios circulan cada día: `calendar.txt` (días de la semana y rango de fechas) más
   las excepciones de `calendar_dates.txt` (p. ej. el 12 de octubre quita el servicio laborable y pone el de
   domingo).
3. Los viajes de EMT son por frecuencias (`frequencies.txt`): «de 07:15 a 20:35 cada 20 min» son 40 salidas. Cada
   salida pasa por todas las paradas del viaje (`stop_times.txt`).
4. Se emite un valor por parada y día, también 0 si ese día no pasa ningún autobús. Los días fuera de la vigencia
   del feed no generan filas: la regla de huecos los señala en lugar de leerlos como «sin autobuses».

## Limitaciones

- Un GTFS es una foto del horario vigente: una ventana pasada se calcula con el horario actual si cae dentro de
  su vigencia. El zip queda en bronze con su SHA-256, así que se puede saber qué versión produjo cada dato.
- Es servicio **programado**, no real: el tiempo real (GTFS-RT) sería otra fuente.

Prueba real (2026-10-24, 30 días): feed vigente del 08/09 al 31/12/2026; 875 paradas × 30 días sin huecos. Un día
laborable suma unos 78.000 pasos de autobús por parada (79.500 los viernes, con el servicio `VIE`) y un domingo
52.800; la parada con más servicio tiene 488 autobuses al día. Fixture en `tests/fixtures/`: el feed real reducido
a las líneas 1 y CC.
