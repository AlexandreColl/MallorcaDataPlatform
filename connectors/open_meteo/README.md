# Open-Meteo

- **API**: <https://open-meteo.com/en/docs/air-quality-api> y <https://open-meteo.com/en/docs>
- **Autenticación**: ninguna (uso no comercial).
- **Datasets**: `air_quality` (modelo CAMS Europa, ~11 km, con polen, polvo sahariano y UV) y `weather` (modelos
  meteorológicos).
- **Frecuencia**: horaria. La API de previsión sirve los últimos 92 días; los anteriores salen de su archivo
  (ver *Histórico*), así que una ejecución pide hasta un año (`max_days: 366`) y el *catch-up* sigue en 92 días.
- **Puntos**: las `locations` de la región (6 en Mallorca), en una sola petición por dataset.

| Métrica | Unidad | Rango válido |
|---|---|---|
| pm10, pm2_5, nitrogen_dioxide, ozone | ug/m3 | ver `connector.yaml` |
| european_aqi | eaqi | 0-500 |
| olive_pollen, grass_pollen | grains/m3 | 0-10.000 y 0-5.000 (las trampas cuentan miles en los picos) |
| dust | ug/m3 | 0-5.000 (polvo sahariano cerca del suelo) |
| uv_index | uvi | 0-20 |
| temperature_2m | degC | -15 a 50 |
| relative_humidity_2m | pct | 0-100 |
| precipitation | mm | 0-300 |
| wind_speed_10m | km/h | 0-250 |
| surface_pressure | hPa | 900-1100 |

## Histórico

`make backfill CONNECTORS=open_meteo START=2017-01-01 END=...` carga los años anteriores, uno por ejecución.

- **Calidad del aire**: la misma API sirve el modelo CAMS Europa desde 2013, sin cambiar nada. El polvo, el polen y el
  UV empiezan más tarde (ver abajo): `options.available_since` del YAML fija el primer día de cada uno, así que una
  ventana anterior no los pide y las horas previas, siempre nulas, no se guardan como valores ausentes.
- **Meteorología**: las ventanas que empiezan antes de los 92 días de la API de previsión piden
  `historical-forecast-api.open-meteo.com`, el archivo de las mismas previsiones (`history_url` en `connector.yaml`).
  - Desde el 16-11-2022 coincide hora a hora con la serie en vivo: probado del 20 al 23-11-2026 en Palma, 96 de 96
    horas iguales, y las alturas de los 6 puntos son las mismas.
  - Antes de ese día el archivo sirve ERA5, el reanálisis del ECMWF (~25 km): es igual, hora a hora, que
    `archive-api.open-meteo.com`. El sesgo del modelo frente a una estación cambia de nivel ese día: en la
    temperatura media diaria (`fct_model_bias_daily`, ajustada por altitud), Cala Millor pasa de −0,92 °C con ERA5
    (1.989 días desde 2017) a −1,54 °C con las previsiones (1.433 días), y Platja de Muro de 0,02 a 0,65 °C.
- Un año de los 6 puntos son 8.760 horas sin nulos en las dos APIs y tarda menos de un segundo por petición.

## Polen, polvo sahariano y UV

La API de calidad del aire sirve también el polen, el polvo del Sáhara y el índice UV del mismo modelo CAMS. Se piden
en la misma petición que el resto del dataset `air_quality`, sin otra URL: la API no tiene un archivo aparte para
ellos, y los días antiguos salen igual que los de la previsión.

- **Métricas**: `olive_pollen` y `grass_pollen` (granos/m³), `dust` (polvo cerca del suelo, µg/m³) y `uv_index`.
- **Gold**: `fct_pollen_dust_daily` da la media y el máximo de cada punto y día, y el nivel de polen de la media diaria
  con los umbrales de la Red Española de Aerobiología (olivo: bajo 1-50, moderado 51-200, alto > 200; gramíneas:
  bajo 1-25, moderado 26-50, alto > 50). `fct_dust_episodes` agrupa los días de polvo (la media de los puntos llega a
  25 µg/m³, la mitad del límite diario de PM10) en episodios y les pone al lado el PM10 de las estaciones de la EEA;
  `agg_dust_pm10_by_station` resume cada estación.
- **Detectores de anomalías**: no las puntúan (`skip.metrics` en `config/anomaly.yaml`). Son cero casi siempre (fuera
  de temporada, entre episodios, de noche) y sus picos son el fenómeno, no un fallo: en Palma, en 2025, el voto marcaba
  el 13,1 % de las horas de UV, el 4,0 % de las de polvo y gramíneas y el 1,0 % de las de olivo, frente al 2,1 % del
  PM10. Los umbrales documentados de gold hacen ese trabajo.

## Lo que enseñaron las pruebas reales (2026-11-28)

Probado año a año en Palma (39,57, 2,65) con las nueve variables de la API, de 2013 a 2026, y luego cargado entero.

- **Cada variable empieza en un día distinto.** El polvo, el 1-1-2018; el polen de olivo, gramíneas, abedul y
  ambrosía, el 7-10-2020 (el aliso el 25-11-2020 y la artemisa el 9-6-2021); `uv_index` y `uv_index_clear_sky`, el
  4-8-2022. Antes de esos días la API responde 200 con la serie entera a `null`. Por eso `available_since`: sin él,
  un backfill de 2017 guardaría 8.760 horas vacías por punto y métrica, y la regla de huecos las contaría.
- **El polen no es solo previsión.** Los días antiguos tienen valores, pero hasta noviembre de 2023 solo en su
  temporada: el olivo de enero a junio y las gramíneas de marzo a agosto, con `null` el resto del año. Desde el
  21-11-2023 llega todo el año (con ceros fuera de temporada). Esos `null` de temporada se guardan como ausentes:
  son 46.650 horas de olivo y 37.290 de gramíneas en los 6 puntos.
- **Por qué solo olivo y gramíneas.** Son los pólenes que importan en Mallorca. Abedul y aliso no son ~0 en el
  modelo, pero casi no crecen en la isla: lo que da CAMS son penachos de fuera. En Palma, desde 2021, la media diaria
  del abedul llega como mucho a 25,3 granos/m³ (16-4-2022, 5 días por encima de 10), la del aliso a 7,6, la de la
  artemisa a 10,6 y la de la ambrosía a 2,8. `uv_index_clear_sky` (el UV sin nubes, teórico) tampoco se guarda.
- **El olivo depende mucho del punto.** La media diaria más alta es de 218 granos/m³ en Sóller y 166 en Inca, entre
  olivares, frente a 55 en Palma. Por eso el nivel moderado (≥ 51) aparece 87 veces en un punto y un día (2 de ellas
  alto), casi todas en Sóller (hasta 17 días al año) e Inca, y casi nunca en la media de la isla. Las gramíneas no pasan
  de 17 granos/m³ de media diaria en ningún punto: siempre nivel bajo. CAMS, a ~11 km, se queda corto frente a lo que
  cuentan los captadores de polen, que miden en un punto; sirve para ver la temporada, no para el aviso de un día.
- **La temporada.** El olivo, de mediados o finales de abril a mediados de junio, con el pico en mayo: 85,0 granos/m³
  de media en la isla el 16-5-2021 y 71,6 el 29-5-2026. Las gramíneas, de finales de marzo a mediados de agosto, con
  picos de 8 a 14.
- **El polvo de 2018 parece de otro modelo.** Su media diaria de la isla no pasa de 12,2 µg/m³, cuando de 2019 a 2026
  el máximo de cada año va de 36 a 78. Ningún día de 2018 llega al umbral: tómese 2018 con cuidado.
- **Los episodios de polvo.** 24 episodios con 44 días de 2019 a noviembre de 2026, de 2 a 10 días al año. El más
  cargado, del 22 al 25 de enero de 2020 (90,4 µg/m³ de media diaria en Sóller), es anterior al PM10 de la EEA. En
  los 19 con estaciones, su PM10 medio sube de 20,1 µg/m³ en los días sin polvo de alrededor a 56,2 durante el
  episodio, 36 µg/m³ más. El del 20 y 21 de marzo de 2025 llegó a 185 µg/m³ de polvo en una hora y llevó las 7
  estaciones de 15,2 a 92,8 µg/m³.
- **CAMS se queda corto en el PM10 los días de polvo.** Durante los episodios, el PM10 del modelo está 5,6 µg/m³ por
  debajo de las estaciones de media, y 32,3 en marzo de 2025. Por estación, el sesgo empeora de los días normales a los
  de polvo en Sa Pobla (−5,2 a −12,3), Alcúdia (−3,2 a −8,7) y el Hospital Joan March (−2,2 a −6,7); en Bellver y
  Foners apenas cambia. Un hueco de PM10 que se rellena con CAMS un día de polvo (`config/corrections.yaml`) sale,
  por tanto, bajo.
- **El UV.** Máximo de 10,4 en julio, y de 59 a 77 días al año con un máximo de 8 o más (muy alto) en cada punto.

**Limitación**: son datos de modelo, no medidas de estación. Sirven como referencia y para inyectar
fallos de forma controlada (Plan B de la fase de anomalías).

Prueba real (2026-10-24): 2 puntos x 24 h x 10 métricas, 0 nulos. Fixtures en `tests/fixtures/`; la de calidad del
aire se volvió a grabar el 2026-11-28 con la misma petición y las cuatro métricas nuevas (2 x 24 x 9).
