# AEMET (estaciones oficiales)

- **Fuente**: AEMET OpenData, valores climatológicos diarios: <https://opendata.aemet.es>
- **Autenticación**: API key gratuita que se pide por correo. Va en `.env` como `AEMET_API_KEY` y se envía en la
  cabecera `api_key`; nunca se guarda en bronze ni en los logs. Sin la clave, el conector queda fuera de la
  selección por defecto del DAG; si se pide explícitamente, falla indicando la variable que falta.
- **Datos**: **observación real** de la red oficial: un valor diario por estación (33 estaciones en Mallorca).

| Campo AEMET | Métrica | Unidad |
|---|---|---|
| `tmed`, `tmin`, `tmax` | `temperature_2m_mean`, `_min`, `_max` | degC |
| `prec` | `precipitation_sum` (07-07 UTC; `Ip`, inapreciable, se guarda como 0) | mm |
| `hrMedia` | `relative_humidity_2m_mean` | pct |
| `velmedia`, `racha` | `wind_speed_10m_mean`, `wind_gusts_10m_max` (m/s × 3,6) | km/h |
| `sol` | `sunshine_duration` | h |
| `presMax`, `presMin` | `pressure_station_max`, `_min` (a la altura de la estación) | hPa |

Las variables que una estación no mide (p. ej. horas de sol) no generan filas.

## Cómo funciona la API

1. **Dos pasos**: la llamada con la clave devuelve un JSON pequeño con `estado` y una URL temporal `datos`; los
   datos se descargan de esa URL, en JSON con codificación ISO-8859-15.
2. **Inventario** de estaciones para saber cuáles caen en la región y sus coordenadas, que los valores diarios no
   traen. Las coordenadas vienen en grados, minutos y segundos (`393339N`).
3. **Valores diarios** en peticiones de hasta 6 meses y hasta **25 estaciones** (límites de la API: «No se permite
   mas de 25 Idemas»). Un objeto de bronze por grupo de estaciones.
4. `estado` 404 («No hay datos que satisfagan esos criterios») es una respuesta vacía; cualquier otro error falla.

## Retraso de publicación

AEMET publica los valores diarios con 2-3 días de retraso. El conector declara `lag_days: 3`: su ventana termina 3
días antes de ayer, así que `days: 1` pide el último día ya publicado y la recuperación de días perdidos nunca da
por cargado un día que aún no existía.

## Limitaciones

- Las observaciones horarias (`/observacion/convencional`) solo cubren las últimas horas, nunca un día completo
  anterior: no se usan.
- Algunas estaciones faltan algunos días o no miden todas las variables; la regla de huecos lo señala.

Prueba real (2026-10-24, 30 días): 30 de las 33 estaciones con datos, 6.575 valores. En el temporal del 19 de
octubre cayeron 79,2 mm en Es Capdellà y 72,2 mm en Sant Elm. Fixtures en `tests/fixtures/`: inventario de Baleares
y valores diarios reales de Palma (aeropuerto y puerto) y Port de Sóller.
