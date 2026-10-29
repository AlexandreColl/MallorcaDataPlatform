# Calidad del aire de la EEA (estaciones oficiales de Mallorca)

- **Fuente**: [Air Quality Download Service](https://eeadmz1-downloads-webapp.azurewebsites.net/) de la Agencia
  Europea de Medio Ambiente: los datos *up-to-date* (E2a, sin validar) que las redes nacionales envían cada hora. En
  Mallorca son las estaciones de la red del Govern.
- **Autenticación**: ninguna.
- **Datos**: horarios, unas dos horas por detrás del tiempo real, en µg/m³.

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

1. `extract` hace una búsqueda JSON (`POST /ParquetFile/urls`) por país, contaminantes y fechas. La respuesta es la
   lista de ficheros Parquet, uno por punto de muestreo (estación y contaminante) con el año en curso. Se descargan
   los de las estaciones del YAML y cada uno se guarda **sin tocar** en bronze (base64, con su SHA-256), con el punto
   de muestreo como partición.
2. `normalize` lee el Parquet con pyarrow y se queda con las horas de la ventana:
   - Las horas de los ficheros españoles son UTC+01 fijo (el *Timezone* de los metadatos de la EEA), así que
     10:00-11:00 son las 09:00 UTC.
   - Las filas que la fuente marca como no válidas (validez -1 o -99) llevan el valor centinela -999 y se guardan
     como `missing`, no como un valor.
3. Las estaciones de Baleares que no están en el YAML se ignoran con un aviso en el log, así que una estación nueva
   no pasa desapercibida.

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
- **Bronze**: cada fichero trae el año entero, así que una ejecución guarda unos 4 MB en bronze aunque la ventana
  sea de un día.
- **Datos sin validar**: los valores verificados (E1a, años anteriores) son otro dataset (`dataset: 2`).

Prueba real (2026-10-29, 30 días):

- 8 estaciones, 32 puntos de muestreo y 20.239 valores horarios, en 46 s.
- La regla de huecos marca alrededor del 20 %: la fuente no tiene datos del 15 al 18 de octubre, más las horas no
  válidas.
- 28 valores quedan fuera de rango: ruido negativo de los analizadores.

Frente al modelo:

- El modelo se queda corto de NO₂ junto al tráfico de Foners (−6,2 µg/m³).
- Se pasa de ozono en Palma: +19,7 en Foners y +21,0 en Son Llàtzer. Es lo esperable: el NO del tráfico consume
  ozono y el modelo no lo resuelve.
- PM10 queda ligeramente corto en todas las estaciones.

Fixtures en `tests/fixtures/`: el listado real de la búsqueda (Baleares y tres ficheros de Madrid) y cinco ficheros
reales recortados al 10-20 de octubre de 2026, con el corte de la fuente incluido.
