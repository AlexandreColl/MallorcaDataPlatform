# Open-Meteo

- **API**: <https://open-meteo.com/en/docs/air-quality-api> y <https://open-meteo.com/en/docs>
- **Autenticación**: ninguna (uso no comercial).
- **Datasets**: `air_quality` (modelo CAMS Europa, ~11 km) y `weather` (modelos meteorológicos).
- **Frecuencia**: horaria. La API de previsión sirve los últimos 92 días; los anteriores salen de su archivo
  (ver *Histórico*), así que una ejecución pide hasta un año (`max_days: 366`) y el *catch-up* sigue en 92 días.
- **Puntos**: las `locations` de la región (6 en Mallorca), en una sola petición por dataset.

| Métrica | Unidad | Rango válido |
|---|---|---|
| pm10, pm2_5, nitrogen_dioxide, ozone | ug/m3 | ver `connector.yaml` |
| european_aqi | eaqi | 0-500 |
| temperature_2m | degC | -15 a 50 |
| relative_humidity_2m | pct | 0-100 |
| precipitation | mm | 0-300 |
| wind_speed_10m | km/h | 0-250 |
| surface_pressure | hPa | 900-1100 |

## Histórico

`make backfill CONNECTORS=open_meteo START=2017-01-01 END=...` carga los años anteriores, uno por ejecución.

- **Calidad del aire**: la misma API sirve el modelo CAMS Europa desde 2013, sin cambiar nada.
- **Meteorología**: las ventanas que empiezan antes de los 92 días de la API de previsión piden
  `historical-forecast-api.open-meteo.com`, el archivo de las mismas previsiones (`history_url` en `connector.yaml`).
  - Desde el 16-11-2022 coincide hora a hora con la serie en vivo: probado del 20 al 23-11-2026 en Palma, 96 de 96
    horas iguales, y las alturas de los 6 puntos son las mismas.
  - Antes de ese día el archivo sirve ERA5, el reanálisis del ECMWF (~25 km): es igual, hora a hora, que
    `archive-api.open-meteo.com`. El sesgo del modelo frente a una estación puede cambiar de nivel ese día.
- Un año de los 6 puntos son 8.760 horas sin nulos en las dos APIs y tarda menos de un segundo por petición.

**Limitación**: son datos de modelo, no medidas de estación. Sirven como referencia y para inyectar
fallos de forma controlada (Plan B de la fase de anomalías).

Prueba real (2026-10-24): 2 puntos x 24 h x 10 métricas, 0 nulos. Fixtures en `tests/fixtures/`.
