# Open-Meteo

- **API**: <https://open-meteo.com/en/docs/air-quality-api> y <https://open-meteo.com/en/docs>
- **Autenticación**: ninguna (uso no comercial).
- **Datasets**: `air_quality` (modelo CAMS Europa, ~11 km) y `weather` (modelos meteorológicos).
- **Frecuencia**: horaria. Máximo 92 días hacia atrás.
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

**Limitación**: son datos de modelo, no medidas de estación. Sirven como referencia y para inyectar
fallos de forma controlada (Plan B de la fase de anomalías).

Prueba real (2026-10-24): 2 puntos x 24 h x 10 métricas, 0 nulos. Fixtures en `tests/fixtures/`.
