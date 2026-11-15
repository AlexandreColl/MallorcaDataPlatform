# SOCIB (estaciones meteorológicas y boyas de oleaje)

- **Fuente**: servidor THREDDS de SOCIB, NetCDF Subset Service para series de puntos (`/ncss/point/`, antes `/ncss/`, que da 404 desde noviembre de 2026) en CSV: <https://thredds.socib.es/thredds>
- **Autenticación**: ninguna. La API REST de SOCIB (`api.socib.es/entries`) exige clave; THREDDS es abierto.
- **Datos**: **observaciones reales** (no modelo), cada 1 min en estaciones y cada 10 min en la boya, con el
  indicador de calidad de SOCIB por variable (`QC_<VAR>`: 1 bueno, 2 probablemente bueno, 3-4 malo, 9 ausente).

| Estación (`entity`) | Tipo | Carpeta THREDDS |
|---|---|---|
| `parcbit` | estación (Palma) | `mooring/weather_station/station_parcbit-scb_met023` |
| `cala_millor` | estación costera | `mooring/weather_station/mobims_calamillor-scb_met012` |
| `muro` | estación costera | `mooring/weather_station/mobims_muro-scb_met016` |
| `bahia_de_palma_buoy` | boya (tiempo) | `mooring/weather_station/buoy_bahiadepalma-scb_met029` |
| `bahia_de_palma_buoy` | boya (oleaje) | `mooring/waves_recorder/buoy_bahiadepalma-scb_wave006` |
| `portocolom_buoy` | boya (oleaje) | `mooring/waves_recorder/buoy_portocolom-scb_wave008` |

La boya de la bahía tiene dos instrumentos en el mismo sitio, y los dos usan la misma entidad: así el tiempo y el
oleaje de ese punto van juntos (por ejemplo, para el Isolation Forest).

| Variable SOCIB | Métrica | Unidad | Agregación horaria |
|---|---|---|---|
| `AIR_TEM` | `temperature_2m` | degC | media |
| `REL_HUM` | `relative_humidity_2m` | pct | media |
| `AIR_PRE` | `pressure_msl` | hPa | media |
| `WIN_SPE` | `wind_speed_10m` | km/h (m/s × 3,6) | media |
| `WIN_SPE_GUS` | `wind_gusts_10m` | km/h (m/s × 3,6) | máximo |
| `WAV_HEI_SIG` | `wave_height` | m | media (cada 30 min) |
| `WAV_HEI_MAX` | `wave_height_max` | m | máximo |

La dirección del oleaje (`WAV_FRO_DIR`) no se lee: la media horaria de ángulos no tiene sentido (350° y 10° darían
180°).

Los nombres y unidades coinciden con Open-Meteo, así que estación y modelo se comparan directamente
(panel *estación real vs modelo* en Grafana).

## Cómo funciona

1. Por estación, lee el catálogo THREDDS y elige el `*_latest.nc` del despliegue más reciente (`depNNNN` más
   alto): los números de despliegue cambian cuando SOCIB sustituye un instrumento.
2. Lee el atributo `time_coverage_start` del NcML del fichero. El `dataset.xml` de NCSS también lo trae, pero desde
   noviembre de 2026 el servidor a veces lo omite. El fichero `latest` empieza el día 1 del mes anterior.
3. Los días anteriores salen del archivo: el catálogo de cada año (`L1/<año>/catalog.xml`) lista un fichero por mes
   y despliegue (`..._L1_<año>-<mes>.nc`; un mes con cambio de instrumento tiene dos). Cada fichero se pide solo
   para los días de la ventana en ese mes. Un año sin carpeta (la estación aún no existía, 404) no da nada, y un
   fichero sin muestras esos días (NCSS responde 400, *No features*) se salta.
4. Descarga el CSV con cada variable y su QC. El CSV crudo se guarda en bronze: el del `latest` en la partición de
   la estación, y cada fichero del archivo en la suya (`parcbit-2026-08_dep0001`).
5. `normalize` agrega por hora usando solo muestras con QC 1-2. Si menos del 50 % de las muestras de la hora son
   buenas, la hora queda `suspect` con motivo `source_qc`; si ninguna es buena, `missing`.

## Limitaciones

- Mareógrafo: no hay. Las carpetas `sea_level` de Mallorca están vacías desde 2024, y los `tide_gauge` de Porto
  Cristo, Colònia de Sant Pere y Sa Rápita terminan en 2019-2020.
- Boyas de oleaje de Sóller, Cala Millor, Muro, Son Bou y Playa de Palma: sus últimos datos son de 2015 a junio de
  2026, así que no se configuran.
- `AIR_PRE` está reducida al nivel del mar; Open-Meteo `surface_pressure` no, por eso se llama `pressure_msl`.

Prueba real (2026-10-24): ParcBit 1.440 muestras/día, todas con QC 1; la boya 144 muestras/día, 13 sin dato
(QC 9), y la hora 00h queda `suspect` (2 de 6 muestras buenas). Fixtures en `tests/fixtures/`.
