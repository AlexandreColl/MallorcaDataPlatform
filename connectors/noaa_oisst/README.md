# NOAA OISST (temperatura del mar por satélite)

- **Fuente**: NOAA *Daily Optimum Interpolation Sea Surface Temperature* v2.1 (OISST), de NOAA NCEI: satélite
  (AVHRR), barcos y boyas mezclados en una rejilla global de 0,25° con un análisis por día UTC desde el 1-9-1981.
  Se lee del ERDDAP de NOAA CoastWatch (<https://coastwatch.pfeg.noaa.gov/erddap>), y los días que le faltan, de la
  copia de NOAA PSL por OPeNDAP.
- **Autenticación**: ninguna.
- **Licencia**: dominio público, como los datos del Gobierno de EE. UU. NOAA pide citar el producto (Huang, B. et
  al., 2021, *Improvements of the Daily Optimum Interpolation Sea Surface Temperature (DOISST) Version 2.1*, Journal
  of Climate 34) y su ERDDAP avisa de que no da garantías sobre el dato ni sirve para usos legales.
- **Puntos**: los 8 puntos de costa de Open-Meteo Marine, con el mismo nombre de entidad para comparar 1:1. Cada uno
  lee la celda de OISST más cercana que es mar en la máscara de tierra de la rejilla (de 5 a 21 km del punto). Las
  boyas de SOCIB de la bahía de Palma y Portocolom caen en las celdas de `bahia_de_palma` y `portocolom`.
- **Frecuencia**: diaria (`frequency: 1d`).

| Métrica | Producto | Unidad | Rango válido |
|---|---|---|---|
| sea_surface_temperature | definitivo (`ncdcOisst21Agg_LonPM180`), desde 1981 | degC | 0-35 |
| sea_surface_temperature_preliminary | provisional (`ncdcOisst21NrtAgg_LonPM180`), desde el 4-5-2020 | degC | 0-35 |

## Cómo lee los datos

- **Dos productos**. El definitivo llega unos 16 días tarde; el provisional, al día siguiente. Cada ejecución pide a
  los dos su último día publicado (`time[last]`, unos bytes), lee el definitivo hasta ese día y el provisional para
  los días posteriores. Un día que ninguno tiene todavía se deja para la siguiente ejecución, que lo vuelve a pedir.
- **Una caja por ventana, no una petición por punto**: ERDDAP sirve en CSV cualquier caja de la rejilla. Las celdas
  de los 8 puntos caben en 3 × 5 celdas (39,375-39,875 N, 2,375-3,375 E): cinco años son unos 0,8 MB y 30 s. Las
  celdas que no son de ningún punto se descartan al normalizar.
- **Cada valor lleva el día que describe, a las 00:00 UTC**. OISST analiza días UTC y ERDDAP los sella a las 12:00
  UTC, la mitad del día. El conector los guarda al inicio de ese día UTC, que en Mallorca es la 01:00 o las 02:00 del
  mismo día: la fecha local coincide con la del análisis. Los marts de gold usan esa fecha UTC (`day`).
- **Un valor provisional no se sobrescribe con el definitivo: son dos métricas**. Gold toma el definitivo cuando
  existe y marca los días que aún son provisionales (`is_preliminary`). `min_days: 21` hace que cada ejecución
  vuelva a leer sus últimas tres semanas, así que el definitivo de un día llega en cuanto se publica.
- **Huecos de ERDDAP rellenados desde PSL**: el eje de tiempo del producto definitivo en ERDDAP tiene agujeros que
  los ficheros de NOAA no tienen. El conector pide esos días a la copia de NOAA PSL
  (`psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres`, un fichero por año, en texto OPeNDAP), en tramos de
  31 días como mucho (`psl_max_days`). Un fallo de PSL se registra y deja el hueco: no hace fallar la ejecución.
- **Histórico**: `max_days: 1830`, así que
  `make backfill CONNECTORS=noaa_oisst START=1981-09-01 END=<ayer> CHUNK_DAYS=1826` carga los 45 años en diez
  ejecuciones.

## Lo que enseñaron las pruebas reales

Probado el 26-11-2026 contra ERDDAP y PSL, con el histórico entero cargado en local.

- **El definitivo llega 16 días tarde; el provisional, 1.** El 26-11-2026 el último día definitivo era el 10-11 y el
  último provisional, el 25-11. Pedir un día que aún no existe da HTTP 404 con *"greater than the axis maximum"*: por
  eso el conector pregunta antes `time[last]`, y si aun así llega ese 404 (el servidor se actualizó entre las dos
  peticiones) lo trata como «todavía no publicado», no como un fallo. `lag_days: 0` porque un día que falta no rompe
  la ejecución: la siguiente lo vuelve a pedir.
- **El provisional apenas cambia al hacerse definitivo.** En los 358 días entre el 1-11-2025 y el 10-11-2026 que
  tienen los dos, en las 11 celdas de mar de la caja: sesgo 0,00 °C, error medio 0,11 °C, máximo 1,17 °C.
- **ERDDAP redondea el tiempo al día más cercano**: pedir `(1995-08-01)` (medianoche) devuelve el 31-7 a las 12:00,
  que está a la misma distancia. El conector pide siempre `T12:00:00Z`.
- **El eje de tiempo de ERDDAP tiene agujeros**: faltaban 1.196 días del definitivo, casi todos entre octubre de 1992
  y 1998 (en 1994 solo tenía 138 días) y unos pocos en 2021-2026. Los ficheros de NOAA sí los tienen
  (`oisst-avhrr-v02r01.19921012.nc` existe en NCEI), y la copia de PSL también, con los mismos valores donde los dos
  tienen dato (21,04 °C frente a Palma el 10-10-1992 en ambos). Tras rellenarlos, silver tiene los 16.507 días del
  1-9-1981 al 10-11-2026 en los 8 puntos, sin un hueco.
- **PSL lee su fichero anual a unos 0,3 s por día**: un año entero (unos 2 minutos) pasa el tiempo de lectura de 60 s
  del cliente HTTP. En tramos de 31 días son unos 10 s por petición, y rellenar 800 días, unos 4 minutos.
- **No hay otro ERDDAP de respaldo**: `upwell.pfeg.noaa.gov` responde a las mismas URL con una redirección a
  `coastwatch.pfeg.noaa.gov` (el mismo servidor), y los ERDDAP de `coastwatch.noaa.gov`, PacIOOS, PolarWatch y
  OceanWatch no tienen OISST. PSL hace de respaldo solo para los huecos.
- **La máscara de tierra de 0,25° es gruesa**: en la caja de 39,125-40,375 N y 1,875-3,875 E solo 4 celdas son tierra
  (39,625 N con 2,625, 2,875 y 3,125 E, y 39,875 N 3,125 E). El punto de la bahía de Palma cae junto a una de ellas y
  lee la de 39,375 N, 2,625 E, a 15 km; Pollença y Alcúdia, a 21 y 19 km, leen celdas distintas. Los valores de una
  celda de costa son los de un cuadrado de unos 28 × 21 km, no los de la playa.
- **Los gaps de la regla de calidad son por producto**: en una ventana de 2026 el definitivo cubre hasta el día 10 y
  el provisional desde el 11, así que la regla `gaps` cuenta huecos en cada métrica. Es informativa y no para la
  carga.

Lo que dice el dato (1-9-1981 a 24-11-2026, 8 puntos):

- **La climatología 1991-2020** va de 13,9-14,1 °C a finales de febrero a 25,9-26,3 °C a mediados de agosto, y el
  percentil 90 queda unos 1,2 °C por encima.
- **El mar se ha calentado**: la anomalía media por década pasa de −0,48 °C en los ochenta y los noventa a +0,43 °C en
  2010-2019 y +1,05 °C desde 2020. Los años más cálidos son 2026 (+1,62 °C hasta noviembre), 2025 (+1,42), 2022
  (+1,41) y 2023 (+1,26); el más frío, 1984 (−1,17).
- **Las olas de calor marinas pasan de raras a habituales**: 1,5 días al año por punto en los ochenta, 13,5 en los
  2000, 49 en 2010-2019 y 136 desde 2020. Frente a la bahía de Palma hay 88 olas desde 1981: 4 antes de 1991 y 59
  desde 2016. Es lo esperable con una referencia fija (1991-2020) y un mar que se calienta.
- **La de 2026 es la más larga**: frente a Palma, del 15-6 al 23-10 (131 días, severa), con 29,88 °C el 7-8-2026, el
  valor más alto de la serie; julio y agosto de 2026 tienen todos sus días en ola de calor en los 8 puntos, con +3,0
  y +2,9 °C. La siguiente es la de 2022 (127 días, del 30-5 al 3-10). La primera severa del registro es de agosto de
  2003. La mayor anomalía de un día, +4,99 °C, es de Sa Dragonera el 1-7-2025.
- **Open-Meteo Marine es algo más cálido que el satélite**: en los 116 días con los dos cargados en local (1-8 a
  24-11-2026), de +0,23 °C (Cala Millor) a +0,58 °C (Sóller) de sesgo, con una correlación de 0,99 en todos los
  puntos.

## Gold

- `dim_sea_temperature_climatology`: la temperatura habitual de cada punto y día del año (1-366, el 29 de febrero es
  siempre el 60) en 1991-2020, con la definición de Hobday et al. (2016): media y percentil 90 de los valores
  definitivos a 5 días o menos de ese día en los 30 años (ventana de 11 días), suavizados con una media móvil de 31
  días que da la vuelta al año. Los parámetros están en `vars` de `dbt_project.yml` (`sst_*`).
- `fct_sea_temperature_daily`: el valor de cada punto y día, su anomalía frente a la climatología y si es día de
  **ola de calor marina**: 5 días seguidos o más por encima del percentil 90; dos separadas por 2 días o menos son
  una sola, con el hueco dentro (islas y huecos, como `fct_weather_episodes`). Un día sin valor corta la racha.
- `fct_marine_heatwaves`: una fila por ola de calor y punto, con sus días, el pico, la intensidad media y acumulada
  (°C × día) y la categoría de Hobday et al. (2018): el pico en múltiplos de la distancia entre el percentil 90 y la
  climatología (1-2 moderada, 2-3 fuerte, 3-4 severa, 4 o más extrema).
- `fct_sea_temperature_monthly`: la media de los puntos por mes, su anomalía y los días de ola de calor, para la web
  (junto a la anomalía de la temperatura del aire) y para Grafana.
- `fct_sst_model_comparison_daily` y `agg_sst_model_bias_by_point`: Open-Meteo Marine (media diaria UTC de sus
  horas, con 20 como mínimo) frente al satélite en cada punto. Las boyas de SOCIB aún no cargan la temperatura del
  agua, así que no se comparan.

API: `GET /v1/sea/temperature/daily`, `GET /v1/sea/temperature/monthly` (en caché) y `GET /v1/sea/heatwaves`.

## Fixtures

```bash
make record-fixtures CONNECTOR=noaa_oisst DAYS=21
```

Grabadas el 26-11-2026: del 4 al 24-11-2026, el definitivo hasta el 10 y el provisional del 11 al 24.
