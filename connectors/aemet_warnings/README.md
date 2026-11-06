# AEMET (avisos)

- **Fuente**: avisos meteorológicos de AEMET (Meteoalerta) en formato CAP, desde AEMET OpenData:
  - `/avisos_cap/archivo/fechaini/…/fechafin/…`: el archivo de avisos de toda España;
  - `/avisos_cap/ultimoelaborado/area/64`: la última emisión de Baleares (área 64).
- **Autenticación**: la misma clave gratuita del conector `aemet` (`AEMET_API_KEY` en el `.env`).
- **Datos**: el nivel de aviso de cada zona de Mallorca y fenómeno, hora a hora. El valor es 0 sin riesgo,
  1 amarillo, 2 naranja y 3 rojo.

| Código AEMET | Métrica | Fenómeno |
|---|---|---|
| `PR` | `warning_rain` | Lluvias |
| `TO` | `warning_storms` | Tormentas |
| `VI` | `warning_wind` | Viento |
| `CO` | `warning_coastal` | Fenómenos costeros |
| `AT` / `BT` | `warning_max_temperature` / `warning_min_temperature` | Temperaturas máximas / mínimas |
| `NE`, `NI`, `RI`, `VS` | `warning_snow`, `warning_fog`, `warning_rissaga`, `warning_dust` | Nevadas, nieblas, rissagas, polvo en suspensión |

La `entity` es el código de zona de AEMET y `lat`/`lon` es el centro de su polígono. Mallorca tiene nueve zonas:

| Zona | Tierra | Aguas costeras |
|---|---|---|
| Sierra de Tramontana | `645401` | `645401C` |
| Norte y nordeste | `645402` | `645402C` |
| Interior | `645403` | — |
| Sur | `645404` | `645404C` |
| Levante | `645405` | `645405C` |

Una zona entra si algún vértice de su polígono cae en la región. Las costeras se adentran en el mar, así que su centro
puede quedar fuera. Los polígonos están en el seed `dim_warning_zones`, sacado una vez de los propios avisos.

## Lo que enseñaron las pruebas reales (2026-11-05)

- **Cada emisión es una foto de los avisos en vigor.** El 2 de noviembre a las 01:57 había aviso amarillo por
  lluvias para el día 3 en las cinco zonas de tierra. La emisión de las 10:24 solo lo mantenía en Tramontana y en el
  Sur. En las otras tres el aviso simplemente desapareció, sin un `Cancel` ni un mensaje en verde.
  - Por eso cada hora toma su nivel de la foto en vigor, la última emisión publicada antes de esa hora. Si esa foto no
    tiene mensaje para la zona y el fenómeno, el nivel es 0.
  - Tomar el último mensaje de cada aviso habría dejado esas tres zonas en amarillo para siempre.
- **El archivo tiene dos niveles de empaquetado.** Es un tar con un `.gz` por emisión, y cada uno es a su vez un tar
  comprimido con los CAP de toda España de ese momento. Bronze guarda solo los de Baleares (`*AFAZ64*`), sin
  tocarlos y agrupados por emisión.
- **El archivo no admite rangos de más de 2 días.** Responde *«El rango de fechas no puede ser superior a 2 dias»*.
  Cada petición cubre hasta 2 días de la ventana más el día anterior (`lookback_days`), porque los avisos de un día se
  suelen emitir el día antes.
- **Cada aviso viene dos veces, en español y en inglés.** Se lee el bloque `es-ES`.

## Dos datasets que no se pisan

- **`archive`** escribe las horas de su trozo de ventana con las fotos que estaban de verdad en vigor.
- **`latest`** escribe las horas posteriores a la ventana: hoy y los próximos días, con la última emisión.

Al día siguiente, el archivo vuelve a escribir esas horas con las emisiones que hubo de verdad. Así, el dashboard
enseña los avisos de hoy y de mañana, y el histórico acaba con los definitivos.

`frequency: event`: no se aplica la regla de huecos, porque una zona sin avisos no es un dato perdido. En gold,
`fct_weather_warnings` convierte las horas en periodos (zona, fenómeno, nivel, inicio y fin) con *gaps and islands*.
