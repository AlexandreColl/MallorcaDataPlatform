# SOCIB (estaciones meteorológicas y boyas)

- **Fuente**: servidor THREDDS de SOCIB, NetCDF Subset Service (NCSS) en CSV: <https://thredds.socib.es/thredds>
- **Autenticación**: ninguna. La API REST de SOCIB (`api.socib.es/entries`) exige clave; THREDDS es abierto.
- **Datos**: **observaciones reales** (no modelo), cada 1 min en estaciones y cada 10 min en la boya, con el
  indicador de calidad de SOCIB por variable (`QC_<VAR>`: 1 bueno, 2 probablemente bueno, 3-4 malo, 9 ausente).

| Estación (`entity`) | Tipo | Carpeta THREDDS |
|---|---|---|
| `parcbit` | estación (Palma) | `mooring/weather_station/station_parcbit-scb_met023` |
| `cala_millor` | estación costera | `mooring/weather_station/mobims_calamillor-scb_met012` |
| `muro` | estación costera | `mooring/weather_station/mobims_muro-scb_met016` |
| `bahia_de_palma_buoy` | boya | `mooring/weather_station/buoy_bahiadepalma-scb_met029` |

| Variable SOCIB | Métrica | Unidad | Agregación horaria |
|---|---|---|---|
| `AIR_TEM` | `temperature_2m` | degC | media |
| `REL_HUM` | `relative_humidity_2m` | pct | media |
| `AIR_PRE` | `pressure_msl` | hPa | media |
| `WIN_SPE` | `wind_speed_10m` | km/h (m/s × 3,6) | media |
| `WIN_SPE_GUS` | `wind_gusts_10m` | km/h (m/s × 3,6) | máximo |

Los nombres y unidades coinciden con Open-Meteo, así que estación y modelo se comparan directamente
(panel *estación real vs modelo* en Grafana).

## Cómo funciona

1. Por estación, lee el catálogo THREDDS y elige el `*_latest.nc` del despliegue más reciente (`depNNNN` más
   alto): los números de despliegue cambian cuando SOCIB sustituye un instrumento.
2. Lee el `dataset.xml` del fichero y comprueba que cubre la ventana pedida. El fichero `latest` empieza el día 1
   del mes anterior; si la ventana empieza antes, falla indicando cuántos días se pueden pedir.
3. Descarga el CSV con cada variable y su QC. El CSV crudo, minuto a minuto, se guarda en bronze (una partición
   por estación).
4. `normalize` agrega por hora usando solo muestras con QC 1-2. Si menos del 50 % de las muestras de la hora son
   buenas, la hora queda `suspect` con motivo `source_qc`; si ninguna es buena, `missing`.

## Limitaciones

- Solo el fichero `latest` (de 31 a 61 días hacia atrás según el día del mes). Histórico por ficheros mensuales:
  pendiente (ver ROADMAP).
- `AIR_PRE` está reducida al nivel del mar; Open-Meteo `surface_pressure` no, por eso se llama `pressure_msl`.

Prueba real (2026-10-24): ParcBit 1.440 muestras/día, todas con QC 1; la boya 144 muestras/día, 13 sin dato
(QC 9), y la hora 00h queda `suspect` (2 de 6 muestras buenas). Fixtures en `tests/fixtures/`.
