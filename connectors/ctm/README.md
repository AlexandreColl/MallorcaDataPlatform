# CTM (autobús, tren y metro de toda la isla)

- **Fuente**: GTFS estático del Consorci de Transports de Mallorca (CTM), publicado en la web de TIB:
  <https://www.tib.org/documents/20124/478141/ctm-mallorca-es.zip> (~6,7 MB, CC BY 4.0). Se regenera cada día
  (`feed_version` es la hora de generación).
- **Autenticación**: ninguna.
- **Datos**: 78 líneas (71 de autobús TIB, 3 de tren SFM, el metro M1 y 3 a demanda) y 763 paradas en toda la isla.

| Métrica | Unidad | Qué es |
|---|---|---|
| `scheduled_departures` | vehicles | autobuses, trenes o metros programados que pasan por la parada ese día |
| `lines_served` | lines | líneas distintas que pasan por la parada ese día |

Cada parada es una `entity` (`stop_<stop_id>`) con su posición; `ts` es la medianoche local (Europe/Madrid) del día
de servicio. Las estaciones (`location_type` 1) y sus accesos no son paradas: los trenes paran en sus andenes.

## Cómo funciona

El conector es una subclase de `core/connectors/gtfs.py`, la misma lógica que EMT Palma:

1. `extract` descarga el zip y lo guarda **sin tocar** en bronze (base64, con su SHA-256 y tamaño en la petición).
2. `normalize` decide qué servicios circulan cada día con `calendar.txt` y las excepciones de `calendar_dates.txt`
   (el 8 y el 25 de diciembre muchas líneas cambian el servicio laborable por el de fin de semana).
3. CTM no tiene `frequencies.txt`: cada viaje cuenta una vez en cada parada por la que pasa.
4. Se emite un valor por parada y día, también 0 si ese día no pasa nada.

Los horarios de temporada son servicios con su propio rango de fechas: las líneas de verano (p. ej. la 325
Alcúdia - Cala Rajada) dejan de circular el 31 de octubre y el horario de invierno empieza el 1 de noviembre.

## Limitaciones

- Como en EMT, un GTFS es una foto del horario vigente y es servicio **programado**, no real.
- Algunas paradas de Palma coinciden con las de EMT, pero son de otra red: no se fusionan.

Prueba real (2026-10-28, 30 días): 763 paradas × 30 días sin huecos (45.780 filas, 52 s). Un día laborable suma unos
41.000 pasos por parada y un domingo 34.000-35.500; la parada con más servicio es la Estació Intermodal de Palma
(`stop_984`, 1.028 vehículos al día). Fixture en `tests/fixtures/`: el feed real reducido a cinco líneas (T1, M1,
313, 325 y 343d).
