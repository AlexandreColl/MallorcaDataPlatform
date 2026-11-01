# Calidad del aire de la EEA (estaciones oficiales de Mallorca)

- **Fuente**: [Air Quality Download Service](https://eeadmz1-downloads-webapp.azurewebsites.net/) de la Agencia
  Europea de Medio Ambiente. En Mallorca son las estaciones de la red del Govern. Tiene dos conjuntos de datos, y cada
  año está solo en uno:
  - *up-to-date* (E2a, `dataset: 1`): el año en curso, sin validar, que las redes envían cada hora;
  - verificados (E1a, `dataset: 2`): los años anteriores ya validados por la red, desde 2013 en Mallorca.
- **Autenticación**: ninguna.
- **Datos**: horarios, en µg/m³. Los del año en curso van unas dos horas por detrás del tiempo real.

| Métrica | Contaminante (código EEA) |
|---|---|
| `nitrogen_dioxide` | NO₂ (8) |
| `ozone` | O₃ (7) |
| `pm10` | PM10 (5) |
| `pm2_5` | PM2.5 (6001) |
| `sulphur_dioxide` | SO₂ (1) |
| `carbon_monoxide` | CO (10), que llega en mg/m³ y se pasa a µg/m³ |

Los nombres y unidades coinciden con los de Open-Meteo, así que cada estación se compara directamente con el modelo
CAMS (`fct_air_quality_model_bias_daily`).

| Entidad | Estación | Código EoI | Tipo |
|---|---|---|---|
| `foners` | Foners (Palma) | ES1610A | tráfico, urbana |
| `bellver` | Bellver (Palma) | ES1604A | fondo, suburbana |
| `parc_bit` | UIB-Parc Bit (Palma) | ES1829A | fondo, rural cerca de la ciudad |
| `sant_joan_de_deu` | Sant Joan de Déu (Palma) | ES1995A | industrial, suburbana |
| `hospital_joan_march` | Hospital Joan March (Bunyola) | ES1827A | fondo, rural |
| `sa_pobla` | Sa Pobla | ES0296A | fondo, rural |
| `s_albufera` | S'Albufera (Alcúdia) | ES1093A | industrial, rural |
| `alcudia` | Alcúdia | ES1517A | fondo, rural |
| `menut` | Menut (Escorca) | — | aún no está en los metadatos de la EEA |

## Cómo funciona

1. `extract` parte la ventana por años: los días del año en curso se buscan en los datos *up-to-date* y los
   anteriores en los verificados. Cada búsqueda es un JSON (`POST /ParquetFile/urls`) por país, contaminantes y
   fechas, y la respuesta es la lista de ficheros Parquet, uno por punto de muestreo (estación y contaminante). Se
   descargan los de las estaciones del YAML.
   - Bronze guarda las filas de la ventana de cada fichero, sin cambiar ninguna, como Parquet (base64), con el
     SHA-256 y el tamaño del fichero entero. La partición es el punto de muestreo, con `_verified` detrás en los
     ficheros verificados.
   - Un fichero verificado trae los trece años de golpe (1,4 MB el NO₂ de Foners), así que se descarga una sola vez
     por proceso: un backfill lee los mismos ficheros en cada tramo de 92 días.
2. `normalize` lee el Parquet con pyarrow y se queda con las horas de la ventana:
   - Las horas de los ficheros españoles son UTC+01 fijo (el *Timezone* de los metadatos de la EEA), así que
     10:00-11:00 son las 09:00 UTC.
   - Las filas que la fuente marca como no válidas (validez -1 o -99) llevan el valor centinela -999 y se guardan
     como `missing`, no como un valor.
. Si la ventana no tiene filas y todos los ficheros terminan antes de ella, la EEA ha dejado de publicar por un
   tiempo (pasó del 30 de octubre al 1 de noviembre de 2026): el conector lanza `SourceNotUpdatedError`, con la hora
   del último dato. El E2E lo trata como una API caída (aviso) y la siguiente ejecución recupera los días. Una
   ventana vacía en medio de los ficheros (un corte de la fuente ya superado) no es este caso.

## Por qué la EEA y no OpenAQ ni aqicn

OpenAQ republica estas mismas estaciones, pero para Mallorca solo trae alrededor del 30 % de las horas: entre 8 y 12
al día, repartidas. Además duplica Foners y Bellver con identificadores distintos y exige clave. La EEA es la fuente
original: tiene todas las horas, salvo los cortes de la propia fuente.

aqicn (World Air Quality Index) también trae solo estaciones del Govern atribuidas a la EEA: 7 en Mallorca.
Pero da solo la última hora, sin histórico, y en subíndices AQI de EE. UU. en lugar de µg/m³. Su previsión diaria
sale de un modelo, igual que la de Open-Meteo.

## Limitaciones

- **Coordenadas**: los metadatos de la EEA no traen coordenadas de las estaciones españolas. Las del YAML son las
  que publica OpenAQ para las mismas estaciones, contrastadas con el municipio y el tipo de estación. Hay dos
  excepciones, que salen del listado de estaciones del Govern:
  - `07040006`: OpenAQ la situaba junto a Son Llàtzer, pero el Govern y aqicn la ponen en Sant Joan de Déu.
  - `07003004` (Alcúdia): no estaba en OpenAQ.
- **Estaciones fuera**: `07040007` (Palma) queda fuera hasta conocer su ubicación.
- **Parc Bit**: las coordenadas del Govern están a 1,5 km de las de OpenAQ, que se mantienen.
- **Datos sin validar**: los del año en curso son provisionales. Cuando la EEA publique ese año verificado, un
  `make backfill` de ese año los sustituye en silver, porque la clave (estación, contaminante, hora) es la misma.
- **Año anterior**: la EEA publica los datos verificados de un año en otoño del siguiente, y los *up-to-date* solo
  traen el año en curso. Hasta entonces, el año anterior no está en ninguno de los dos.
- **Solape con la GOIB**: los ficheros verificados empiezan en 2013 y el histórico de la GOIB llega a junio de 2021.
  El backfill empieza en julio de 2021 para que cada mes tenga una sola fuente en `fct_air_quality_monthly`.

Prueba real (2026-10-29, 30 días):

- 9 estaciones, 36 puntos de muestreo y 22.770 valores horarios.
- La regla de huecos marca alrededor del 20 %: la fuente no tiene datos del 15 al 18 de octubre, más las horas no
  válidas.
- 28 valores quedan fuera de rango: ruido negativo de los analizadores.

Frente al modelo:

- El modelo se queda corto de NO₂ junto al tráfico de Foners (−6,2 µg/m³).
- Se pasa de ozono en Palma: +19,7 en Foners y +21,0 en Sant Joan de Déu. Es lo esperable: el NO del tráfico consume
  ozono y el modelo no lo resuelve.
- PM10 queda ligeramente corto en todas las estaciones.
- Alcúdia está a 12 km de su punto del modelo (Pollença): ahí el modelo se queda corto de PM10 (−9,6 µg/m³).

Fixtures en `tests/fixtures/`: el listado real de la búsqueda (Baleares y tres ficheros de Madrid) y cinco ficheros
reales recortados al 10-20 de octubre de 2026, con el corte de la fuente incluido. Además, el listado real de los
ficheros verificados (Baleares y uno de Madrid) y el fichero verificado del NO₂ de Foners recortado al 29-31 de
diciembre de 2025.
