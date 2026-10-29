# Histórico de calidad del aire de la GOIB (estaciones oficiales de Mallorca)

- **Fuente**: [catálogo de datos abiertos del Govern](https://intranet.caib.es/opendatacataleg/), API CKAN, con
  los mesuraments de cada estación de control de la calidad del aire. Licencia CC BY.
- **Autenticación**: ninguna.
- **Datos**: horarios, de 2002 a **junio de 2021**, en µg/m³. Es un histórico: el catálogo no publica nada más
  reciente. Las medidas actuales llegan con [`eea_air_quality`](../eea_air_quality/README.md).

| Métrica | Columna del CSV |
|---|---|
| `nitrogen_dioxide` | `NO2_HI` |
| `ozone` | `O3_HI` |
| `pm10` | `PM10_HI` |
| `pm2_5` | `PM2,5_HI` |
| `sulphur_dioxide` | `SO2_HI` |
| `carbon_monoxide` | `CO_HI`, que llega en mg/m³ y se pasa a µg/m³ |

Cada columna lleva su bandera `FL_<columna>`.

## Estaciones

Son 11 estaciones, con el código, el tipo y las coordenadas del listado de estaciones del propio catálogo. Las
entidades se llaman igual que en `eea_air_quality`, así que una estación es una sola serie entre las dos fuentes.

| Entidad | Estación | Código | Datos |
|---|---|---|---|
| `foners` | Foners (Palma), tráfico | 07040002 | 2002 - jun. 2021 |
| `bellver` | Parc de Bellver (Palma) | 07040003 | 2002 - jun. 2021 |
| `parc_bit` | Parc Bit (Palma) | 07040004 | jun. 2006 - jun. 2021 |
| `sant_joan_de_deu` | Sant Joan de Déu (Palma), industrial | 07040006 | 2011 - jun. 2021 |
| `hospital_joan_march` | Hospital Joan March (Bunyola) | 07010001 | 2003 - jun. 2021 |
| `sa_pobla` | Sa Pobla | 07044001 | 2002 - jun. 2021 |
| `s_albufera` | S'Albufera (Alcúdia), industrial | 07003001 | 2002 - jun. 2021 |
| `alcudia` | Alcúdia | 07003004 | 2002 - jun. 2021 |
| `can_llompart` | Can Llompart (Pollença) | 07042001 | 2002 - jun. 2021 |
| `menut` | Cases de Menut (Escorca), solo ozono | 07019001 | mar. 2015 - jun. 2021 |
| `inca` | Sa Vinyeta (Inca) | 07027002 | 2009 - 2012 (sin ficheros de 2020 y 2021) |

## Cómo funciona

1. El conector está **desactivado** en la ejecución diaria (`enabled: false`). Se carga una vez, por años:

   ```bash
   make backfill CONNECTORS=goib_air_quality START=2002-01-01 END=2021-06-30
   ```

2. `extract` pide a `package_show` la URL del CSV de cada fichero de la estación cuyos años tocan la ventana:
   - El histórico hasta noviembre de 2019.
   - El de 2020.
   - El de 2021.
3. **Bronze**:
   - Se guarda la cabecera y las líneas de los días de la ventana, sin tocar, con el SHA-256 y el tamaño del
     fichero entero. Un fichero de 18 años, guardado entero en cada ejecución anual, ocuparía 18 veces su
     tamaño.
   - Las descargas se reutilizan dentro del mismo proceso: el backfill baja cada fichero una sola vez.
4. `normalize` lee los tres formatos que publica el catálogo:
   - Separador `;` o `,` (con la columna `"PM2,5_HI"` entre comillas). En los ficheros con `;`, la coma es el
     separador de miles (`1,010`).
   - Fecha con el mes delante (`01/22/2016 12:00:00 AM`) o con el día delante (`22/01/2016`).
   - Cabecera `PERÍODE_HI` o `PERIODE_HI`.
5. El periodo 1-24 de cada día es la hora que **empieza** a esa hora en UTC+01 fijo:
   - El periodo 1 del 2 de julio es 01:00-02:00 UTC+01, es decir, las 00:00 UTC.
   - El periodo 24 es la medianoche, la última hora del día en UTC.
   - Se comprobó hora a hora contra los ficheros verificados de la EEA (E1a) de Foners: coinciden todos los
     valores.
6. Solo la bandera `V` es válida. El resto (`N`, `M`, `C`, `Z`, `D`, `T`) y los valores vacíos se guardan como
   `missing`.

## En dbt y Grafana

- `fct_air_quality_monthly` une este histórico con la EEA por estación y contaminante. Un mes es representativo
  con al menos el 75 % de las horas válidas.
- En **Tiempo y entorno**:
  - NO₂ mensual por estación en los últimos 25 años, con el valor límite anual de la UE.
  - Media anual de la isla por contaminante.
- `air_quality_hourly` deja fuera este histórico: es una tabla que se reconstruye en cada ejecución.

## Limitaciones

- **Hueco de julio de 2021 a 2025**: no está ni en este catálogo ni en los datos *up-to-date* de la EEA. Los
  ficheros verificados de la EEA (E1a, `dataset: 2` en `eea_air_quality`) podrían cubrirlo.
- **Estación 07040006**: el catálogo la llama Sant Joan de Déu, en Coll d'en Rabassa. OpenAQ, de donde salen las
  coordenadas de `eea_air_quality`, la sitúa junto a Son Llàtzer, a 3 km. Las dos estaciones existen en la red:
  hasta aclararlo, cada fuente conserva su nombre.
- **Parc Bit**: las coordenadas del catálogo están a 1,5 km de las de OpenAQ.
- Los datos de 2021 son provisionales, según el propio catálogo.
- **Fallos de la fuente** que el conector resuelve:
  - El histórico de Cases de Menut sigue hasta octubre de 2020, igual que su fichero de 2020. Cada fichero se
    queda solo con sus años.
  - El de Hospital Joan March trae 5.103 filas de 2002 sin periodo y con todas las banderas a `N`. Se ignoran.
  - El servidor responde 502 a veces. Los reintentos del cliente HTTP lo absorben.

## Prueba real (2026-10-29)

- 20 ejecuciones anuales de `make backfill`, en unos 45 minutos (la mayor parte es Spark escribiendo en silver).
- 4.975.606 valores válidos en gold, de 11 estaciones.
- La regla de huecos marca entre el 14 % (SO₂) y el 56 % (PM2.5) de las horas: muchos analizadores empezaron
  más tarde que la estación (el PM2.5, en Foners y Hospital Joan March).
- 169 valores fuera de rango, casi todos de SO₂.

NO₂ medio anual (meses representativos):

| | 2002 | 2007 | 2012 | 2017 | 2019 | 2020 |
|---|---|---|---|---|---|---|
| Foners (tráfico) | 52,7 | 45,7 | 37,7 | 37,6 | 31,6 | 24,0 |
| Bellver (fondo) | 14,1 | 13,9 | 10,3 | 11,6 | 10,7 | 7,7 |

Foners pasó de superar el valor límite anual de la UE (40 µg/m³) a quedar muy por debajo, y 2020 marca el
confinamiento. El ozono va en sentido contrario: la media de la isla sube de 56 µg/m³ en 2002 a 70 en 2019.
