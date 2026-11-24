# REDMAR (mareógrafos de Puertos del Estado)

- **Fuente**: servidor THREDDS de Puertos del Estado, <https://opendap.puertos.es/thredds/catalog/catalog.html>
  (carpetas `tidegauge_mall` y `tidegauge_alcu`).
- **Autenticación**: ninguna. Los datos son públicos y gratuitos; hay que citar a Puertos del Estado y avisarle antes
  de un uso comercial (atributo `distribution_statement` de cada fichero).
- **Mareógrafos**: los dos de Mallorca en la red REDMAR, Palma (3851) y Alcúdia (3853). Los de Ibiza, Formentera
  y Mahón quedan fuera de la región.
- **Frecuencia**: horaria. Cada fichero diario trae el nivel del mar cada medio segundo (2 Hz) con su bandera de
  calidad, desde 2009 en los dos.

| Métrica | Unidad | Rango válido |
|---|---|---|
| sea_level | m | 3-6 |

## Cómo lee los datos

- **Un fichero por mareógrafo y día**: `<carpeta>/<año>/<mes>/MIR2Z_<estación>_<AAAAMMDD>.nc4`, de 5,4 MB.
- **OPeNDAP en texto, sin leer el NetCDF**: el conector pide la hora, el nivel y su bandera de uno de cada 120
  valores (`stride`), uno por minuto. Son unos 60 KB por día en 0,15 s, en lugar de los 5,4 MB del fichero.
  - Un fichero de otra longitud responde 400 a esa petición: el conector lee su tamaño (`.dds`) y la repite.
  - Un día sin fichero (404) se salta.
  - Un día que el servidor no puede leer (5xx) también se salta: el fichero de Palma del 1-6-2012 responde siempre
    500. Más de 3 días seguidos (`max_unreadable_days`) son el servidor caído, y la ejecución falla.
- **Media horaria de los minutos buenos**: banderas OceanSITES 1 y 2, entre 3 y 6 m. Con menos de la mitad buenos,
  la hora es `suspect`; sin ninguno, `missing`. El rango deja fuera unos picos de 5 a 9 m de Alcúdia con bandera
  buena (9-9-2009, 20-1-2010 y 25-8-2011); en todos los años desde 2009 el nivel está entre 3,9 y 4,9 m.
- **Un payload por mareógrafo y ventana** en bronze, con el texto de cada día.

## Qué hay que saber del dato

- **El nivel es la altura sobre el cero del puerto** (`sea_level_datum: Harbour Local Datum`), unos 4,2 m en los
  dos. No es la altura sobre el nivel medio del mar: sirve para seguir la marea y los temporales en cada mareógrafo,
  no para comparar los dos entre sí ni con el modelo de Open-Meteo Marine (`sea_level_height_msl`).
- **En 2026 faltan horas enteras**, unas 6 de cada 24, y son las mismas en los dos mareógrafos. Los ficheros de
  2024 y anteriores tienen más del 95 % de los minutos con bandera buena. Medido el 22-11-2026, el 1 y el 15-10-2026
  y el 1-6-2026 frente al 15-6-2024, el 15-1-2019 y el 10-3-2012.
- El servidor publica también análisis de alta frecuencia (`_analysis_HM`, `_analysis_2hz`): la altura de las
  oscilaciones de minutos, como las rissagues. Muchas de sus horas llevan la bandera 4 (dato malo), así que no se
  cargan.

Prueba real (22-11-2026): 2 mareógrafos × 24 horas, 36 horas con valor (entre 4,0 y 4,4 m) y 12 sin ningún minuto.
Fixtures en `tests/fixtures/` (`make record-fixtures CONNECTOR=redmar`).

**Histórico**: `make backfill CONNECTORS=redmar START=2009-01-01 END=...`, un año por ejecución (732 peticiones).
Cargado hasta el 23-11-2026 en 18 ejecuciones (unos 30 min): 273.000 horas, el 97,9 % con valor bueno. Los dos
empiezan en septiembre de 2009; Palma no tiene ficheros de 2016 (la carpeta no existe en el servidor) y a Alcúdia
le faltan unos meses de 2010. Desde 2023 faltan más horas cada año (en Palma, de 272 en 2023 a 888 en 2026).

**Anomalías**: los detectores no confunden la marea con un fallo. En los 30 días hasta el 23-11-2026 el z-score
marca 2 horas y el residuo estacional ninguna; el isolation forest marca el 7,7 %, casi todo el 12 y el 13-11-2026,
un nivel bajo real (3,89 m en Palma) en los dos mareógrafos a la vez.
