# Open-Meteo Marine (oleaje y mar)

- **Fuente**: <https://marine-api.open-meteo.com/v1/marine>, la misma API que `open_meteo` pero con modelos de
  oleaje y océano.
- **Autenticación**: ninguna.
- **Datos**: **modelo**, no observación, cada hora en 8 puntos de mar alrededor de la isla (`options.points` del
  YAML). La API responde con la celda del modelo más cercana (unos 5 km).

| Métrica | Unidad | Qué es |
|---|---|---|
| `wave_height` | m | altura significativa de ola |
| `wave_period` | s | periodo de ola |
| `wave_direction` | deg | dirección de procedencia |
| `swell_wave_height` | m | mar de fondo |
| `sea_surface_temperature` | degC | temperatura del mar |
| `ocean_current_velocity` | km/h | corriente superficial |
| `sea_level_height_msl` | m | nivel del mar (marea y sobreelevación, sin olas) |

## Diseño

Es una subclase de `OpenMeteoConnector` que solo cambia **qué puntos se consultan**. Las localidades de la región
están en el interior, donde los modelos de oleaje no tienen datos, así que este conector usa sus propios puntos de
mar y se queda con los que caen dentro de la región. La petición, el formato de respuesta y la normalización son
los del conector de Open-Meteo.

Un punto queda junto a la boya de SOCIB de la bahía de Palma, para comparar el modelo con la medida real cuando se
añadan las variables de oleaje de la boya.

Prueba real (2026-10-24, 30 días): 8 puntos × 7 métricas, 40.320 filas, sin huecos ni valores fuera de rango. En el
temporal del 19 de octubre la costa norte llegó a 2,6 m de ola (Sóller) y la bahía de Palma, resguardada, a 1,2 m.
Fixture en `tests/fixtures/marine.json`, grabada con la misma petición que construye el conector.
