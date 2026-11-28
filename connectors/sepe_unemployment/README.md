# SEPE (paro registrado)

- **Fuente**: datos abiertos del SEPE (Servicio Público de Empleo Estatal), *Paro registrado por municipios*, un CSV
  por año: `https://sede.sepe.gob.es/es/portaltrabaja/resources/sede/datos_abiertos/datos/Paro_por_municipios_<año>_csv.csv`.
  En datos.gob.es es el conjunto
  [ea0041513-paro-registrado-por-municipio](https://datos.gob.es/es/catalogo/ea0041513-paro-registrado-por-municipio),
  que también tiene cada año en dos XLS semestrales.
  - Cada fichero trae todos los municipios de España (unos 10 MB, ~97.400 líneas por año completo), en latin1,
    separado por `;`, con una línea de título encima de la cabecera y espacios sueltos en los nombres de columna
    (`Código mes `, ` Municipio`, `Paro hombre edad 25 -45 `).
  - Es el paro registrado el último día hábil de cada mes: el total, seis tramos de sexo y edad y cinco sectores.
- **Licencia**: condiciones generales de reutilización de datos.gob.es (artículo 7 del RD 1495/2011, que desarrolla
  la Ley 37/2007), según el [aviso legal](https://sede.sepe.gob.es/portalSede/datos-abiertos/aviso-legal.html) de
  los datos abiertos del SEPE: uso comercial y no comercial, citando «Origen de los datos: Servicio Público de Empleo
  Estatal» y la fecha de la última actualización, sin desnaturalizar los datos ni sugerir que el SEPE apoya el uso.
- **Autenticación**: ninguna.
- **Datos**: 12 series por municipio y mes, desde enero de 2006.

| Métrica | Columna del CSV | Unidad |
|---|---|---|
| `unemployed` | `total Paro Registrado` | `people` |
| `unemployed_men_under_25`, `unemployed_men_25_44`, `unemployed_men_45_plus` | `Paro hombre edad < 25`, `25 -45`, `>=45` | `people` |
| `unemployed_women_under_25`, `unemployed_women_25_44`, `unemployed_women_45_plus` | `Paro mujer edad < 25`, `25 -45`, `>=45` | `people` |
| `unemployed_agriculture`, `unemployed_industry`, `unemployed_construction`, `unemployed_services` | `Paro Agricultura`, `Industria`, `Construcción`, `Servicios` | `people` |
| `unemployed_no_previous_job` | `Paro Sin empleo Anterior` | `people` |

El tramo «25 -45» del SEPE es de 25 a 44 años y «>=45» de 45 en adelante; los seis tramos suman el total, y los
cinco sectores también. La `entity` es el código INE del municipio y `lat`/`lon` el centro de su límite, los mismos
que en `ine_population` y `ine_tourist_housing`. Cada valor va fechado el día 1 de su mes, a medianoche de Madrid.

## Bronze: solo las líneas de Baleares

Un backfill de 21 años bajaría 200 MB para quedarse con el 1 % de las líneas. Como en `goib_air_quality`, el
payload de cada fichero guarda la línea de título, la cabecera y las líneas de la provincia 7 (Illes Balears) de los
meses de la ventana, tal como vienen, con el SHA-256 y el tamaño del fichero entero en `request`. Menorca, Eivissa y
Formentera quedan en bronze aunque `normalize` solo deje los 53 municipios de Mallorca (los del YAML cuyo centro cae
en la región). Un payload por año (`partition=<año>`).

## Los «<5»: nulos que no son huecos

Desde 2022 el SEPE publica toda cifra de 1 a 4 como `<5`, por secreto estadístico; hasta 2021 daba la cifra exacta
(los ficheros de 2006 a 2021 no tienen ni un `<5`). El cero sigue saliendo como `0`. Guardar un `<5` como 5 inventaría
un dato, y como 2 o 2,5 también, así que se guarda como **valor nulo**.

El problema es que un nulo cuenta como fallo de la regla `not_null` y como paso ausente de la regla de huecos: con
6.780 celdas `<5` entre 2022 y 2026, cada carga habría dado decenas de falsas alarmas, como pasó con los nulos de
temporada del polen. Por eso el core aprendió una opción por métrica, **`suppressed_below: 5`**:

- `not_null` no cuenta los nulos de esas métricas (la fila sigue siendo `missing`, porque no tiene valor).
- La regla de huecos cuenta como publicado un mes con fila aunque su valor sea nulo; un mes **sin fila** sigue
  siendo un hueco.

El backfill completo pasa sin un fallo de calidad de 2006 a 2026, salvo los dos huecos reales del SEPE (abajo). En
gold, `fct_unemployment_monthly.is_suppressed` marca un total `<5` y la suma de la isla cuenta aparte esos municipios
(`suppressed_municipalities`): el total de Mallorca se queda corto como mucho en 4 personas por cada uno.

## Ventana y retraso

- **`frequency: 1mo`**: un valor por mes.
- **`lag_days: 50`**: el mes M entra en el fichero de su año hacia el 11-18 de M+1, una semana después de la nota de
  prensa del paro (octubre de 2026 el 11 de noviembre; diciembre de 2023 el 18 de enero de 2024, según el
  `Last-Modified` de cada fichero). Las ventanas acaban 50 días antes de ayer, así que su último mes ya suele estar.
- **`min_days: 120`**: cada ejecución relee los cuatro últimos meses, porque el SEPE revisa los últimos meses del
  fichero después de publicarlos. Normalmente es un fichero; en enero y febrero, dos.
- **`max_days: 3700`**: los backfills van por años (`make backfill ... CHUNK_DAYS=366`).
- **Frescura**: dbt avisa a los 100 días sin carga nueva y el SLA del catálogo es de 120 días (2.880 h).
- **Detectores de anomalías**: la fuente está en `skip.sources` de `config/anomaly.yaml`, como el resto de
  estadísticas mensuales (12 valores al año son pocos para un detector de series).

## En gold, la API, la web y Grafana

- `fct_unemployment_monthly`: municipio y mes, con los subtotales por sexo y edad, el paro por cada 1.000 habitantes
  del padrón (el de ese año o el último publicado), el interanual y la anomalía frente a la media del mismo mes.
- `fct_unemployment_island_monthly`: la suma de los 53 municipios, con la cuota de los servicios. Entra en
  `fct_resources_monthly` (paro, por 1.000 habitantes y anomalía) junto al turismo, el agua y la electricidad.
- `agg_unemployment_seasonality`: por año, el paro medio de invierno (noviembre a febrero) entre el de verano (junio a
  septiembre), para la isla y para cada municipio.
- API: `GET /v1/unemployment/monthly`, `/v1/unemployment/municipalities` (por defecto, los 12 últimos meses) y
  `/v1/unemployment/seasonality?area=mallorca|07xxx`, y las columnas nuevas de `/v1/resources/monthly`.
- Web: en Turismo y recursos, tres correlaciones (turistas, aeropuerto y cruceristas frente al paro, con y sin el
  ciclo anual) y dos paneles (paro frente al aeropuerto y el cociente invierno/verano); en Movilidad, la capa *Paro
  registrado* del mapa de municipios, una línea en la ficha de cada municipio y una columna en la tabla.
- Grafana: paneles 14 y 15 del dashboard Turismo y recursos.

## Lo que enseñaron las pruebas reales (2026-11-28)

- **Hay ficheros de 2006 a 2026, todos con la misma cabecera**, pero con dos diferencias: el código de municipio
  tiene 4 dígitos hasta 2018 (`7040`) y 5 desde 2019 (`07040`), y los `<5` empiezan en 2022. El de 2005 no existe.
- **Dos huecos reales**: el CSV de 2013 acaba en abril (faltan mayo a diciembre) y el de 2020 en noviembre (falta
  diciembre). La regla de huecos lo marca en esos dos años (12 métricas cada uno) y el cociente invierno/verano de
  2013 queda vacío. Los XLS semestrales de datos.gob.es sí tienen esos meses; leerlos pediría un lector de XLS
  (BIFF) que la imagen no tiene.
- **La carga completa son 153.276 valores** (53 municipios × 12 métricas × 241 meses), 6.780 de ellos `<5`.
- **El máximo fue enero de 2012, con 79.396 parados** (90,6 por cada 1.000 habitantes); **el mínimo, mayo de 2026,
  con 20.187** (21,0). Palma tenía 12.571 en enero de 2026, como en la prueba del 26-11-2026.
- **La isla tiene ahora mucho menos paro de invierno que antes**: el cociente invierno/verano era 1,59 en 2006 y
  1,49 en 2019 (casi un 50 % más de parados en invierno), y ha bajado a 1,22 en 2022, 1,13 en 2023, 1,10 en 2024 y
  1,14 en 2025. La caída coincide con la reforma laboral de 2022: los fijos discontinuos entre temporadas no cuentan
  como parados registrados. En la crisis de 2009-2012 el cociente también bajó (1,20-1,25), pero porque el paro de
  verano se disparó. 2020 es el único año con más paro en verano que en invierno (0,90).
- **Por municipio, los más estacionales son los de costa**: Son Servera (1,74 de media en 2022-2025), Capdepera
  (1,72), Alcúdia (1,65) y Santanyí (1,51). Los del interior, como Sineu o Santa Eugènia, no tienen ciclo (0,98-1,00).
- **En octubre de 2026, Inca era el municipio con más paro por habitante** (35,1 por cada 1.000), por delante de
  Sineu, Sencelles y Palma (30,8); los que menos, Deià, Valldemossa y Banyalbufar (8-9).
- **El paro ha envejecido**: los de 45 años o más eran el 33 % en 2007 y son el 55 % en 2025. Los servicios son
  siempre el 70-77 %.
- **Con el turismo** (2016-2026, Pearson en la web): turistas internacionales r −0,57 (−0,70 sin el ciclo anual),
  pasajeros del aeropuerto r −0,66 (−0,79) y cruceristas r −0,62 (−0,66). Sin el ciclo, la relación la dominan 2020
  y 2021: casi sin visitantes y con el paro disparado.

## Grabar las fixtures

```bash
docker compose --profile tools run --rm toolbox python -m core.cli record-fixtures sepe_unemployment --days 400 --max-mb 30
```

Los ficheros enteros pasan del límite de 2 MB de `make record-fixtures`, así que se grabaron con `--max-mb 30` y luego se
recortaron a mano: título, cabecera y las líneas de Palma, Pollença, Escorca y Calvià (Mallorca), Maó y Eivissa (otras
islas) y Abla (Almería, otra provincia). Se guardan byte a byte (`.gitattributes`: `binary`), con sus finales de línea
CRLF. La grabación de 2026-11-28 cubre de octubre de 2025 a octubre de 2026 (ficheros de 2025 y 2026).
