# INE (viviendas turísticas)

- **Fuente**: estadística experimental del INE *Medición del número de viviendas turísticas en España y su
  capacidad*, tabla 39363 (*Viviendas turísticas, plazas y plazas por vivienda turística por municipios*), desde la
  API Tempus: `https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/39363?tip=AM&date=AAAAMMDD:AAAAMMDD&tv=19:<id>…`.
  - El INE cuenta las viviendas anunciadas para estancias turísticas en las principales plataformas de alquiler en
    un mes de referencia.
  - `tip=AM` añade los metadatos de cada serie: el código INE del municipio (`07042` es Pollença) y el concepto.
  - `date` limita los meses de referencia a los de la ventana.
  - `tv=19:<id>` filtra un municipio por su identificador interno de Tempus (`19` es la variable *Municipios*; los
    53 identificadores están en el YAML). La tabla cubre todos los municipios de España: sin filtro, seis años son
    44 MB; con los 53 de Mallorca, 300 KB en unos 2 segundos. Varios `tv` de la misma variable se suman.
- **Licencia**: CC BY 4.0, como el resto del INE.
- **Autenticación**: ninguna.
- **Datos**: tres series por municipio y mes de referencia, desde agosto de 2020.

| Métrica | Concepto (id de Tempus) | Unidad |
|---|---|---|
| `tourist_dwellings` | Viviendas turísticas (`382508`) | `dwellings` |
| `tourist_beds` | Plazas (`382510`) | `beds` |
| `beds_per_dwelling` | Plazas por vivienda turística (`382509`) | `beds/dwelling` |

La `entity` es el código INE del municipio y `lat`/`lon` el centro de su límite, los mismos que en `ine_population`.
Cada valor va fechado el día 1 del mes de referencia, a medianoche de Madrid.

## Meses de referencia irregulares

El INE hace dos recuentos al año, pero los meses han cambiado: agosto de 2020, febrero y agosto de 2021 a 2024, y
desde entonces noviembre de 2024, mayo y noviembre de 2025 y mayo de 2026. Con un espaciado que no es fijo, la regla
de huecos de `1mo` marcaría como huecos los cinco meses sin recuento y una de `6mo` fallaría en el cambio de 2024.

- **`frequency: event`**: como los sismos, el conjunto no tiene regla de huecos y una ventana sin recuento nuevo es
  un resultado válido. Sí tiene las reglas de rango, nulos y duplicados. Las filas son series de un municipio, no
  eventos, así que el conector no está en la variable `event_sources` de dbt: entra en `agg_daily_metrics` y en
  `dim_locations` como cualquier serie.
- **`min_days: 1095`**: cada ejecución relee los tres últimos años, porque el INE revisa las series experimentales
  cuando cambia el método. Son unos 150 KB.
- **`max_days: 2600`**: todo el histórico, desde agosto de 2020, cabe en un único run de backfill.
- **Frescura**: un recuento sale unos seis meses después de su mes de referencia. dbt avisa a los 240 días sin carga
  nueva y el SLA del catálogo es de 400 días.

## En gold y en la web

`fct_tourist_dwellings` pone las tres series en una fila por municipio y mes de referencia, con el cambio frente al
recuento anterior (esté a tres o seis meses) y el peso frente al padrón del mismo año, o del último publicado si el
de ese año aún no ha salido: viviendas por cada 1.000 habitantes y plazas por cada 100. La API lo sirve en
`GET /v1/tourism/dwellings` y la web añade una capa *Viviendas turísticas* al mapa de municipios de Movilidad, con
una columna más en la tabla de municipios.

## Lo que enseñaron las pruebas reales (2026-11-26)

- **Mallorca tenía 14.756 viviendas turísticas en mayo de 2026**, con 92.849 plazas: un 27 % menos que las 20.196
  de agosto de 2020. El mínimo es noviembre de 2025 (13.837). Por cada 1.000 habitantes, de 22,1 a 15,4.
- **Pollença es el municipio con más**: 2.344 viviendas en mayo de 2026, 131,6 por cada 1.000 habitantes. Le siguen,
  por habitante, Escorca, Fornalutx, Búger y Deià, todos por encima de 115.
- **Palma tiene solo 538**, 1,2 por cada 1.000 habitantes: el alquiler turístico en pisos está prohibido en la
  ciudad desde 2018.
- **Las plazas por vivienda van de 4,1 a 8,2** (Palma en agosto de 2022 y Santa María del Camí en mayo de 2026).
- **La carga completa son 2.067 valores**: 53 municipios × 3 métricas × 13 recuentos, sin nulos ni valores
  secretos, y ninguna regla de calidad falla.

## Grabar las fixtures

```bash
make record-fixtures CONNECTOR=ine_tourist_housing
```

La respuesta va a `tests/fixtures/`, listada en `recorded.json` con sus 53 filtros `tv`; los tests la reproducen sin
red. La de 2026-11-26 cubre del 27-11-2023 al 25-11-2026: seis recuentos, de febrero de 2024 a mayo de 2026.
