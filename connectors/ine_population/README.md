# INE (población)

- **Fuente**: padrón continuo del INE, tabla 2860 (*Balears, Illes: Población por municipios y sexo*), desde la API
  Tempus: `https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/2860?tip=AM&date=AAAAMMDD:AAAAMMDD`.
  - `tip=AM` añade los metadatos de cada serie, donde está el código INE del municipio (`07040` es Palma). El nombre
    de la serie solo trae el nombre del municipio.
  - `date` limita los años a los de la ventana.
- **Autenticación**: ninguna.
- **Datos**: la población de cada municipio de Mallorca a 1 de enero, en total y por sexo. Hay padrón desde 1996,
  salvo en 1997.

| Métrica | Valor de «Sexo» | Unidad |
|---|---|---|
| `population` | `0` Total | `people` |
| `population_men` | `1` Hombres | `people` |
| `population_women` | `2` Mujeres | `people` |

La `entity` es el código INE del municipio, y `lat`/`lon` el centro de su límite. La tabla cubre los 67 municipios de
Baleares. El YAML lista los 53 de Mallorca con su centro, y el conector se queda con los que caen dentro de la región.
El total balear de la tabla se descarta: el de Mallorca es la suma de sus municipios, y lo calcula gold.

## Frecuencia anual

Es la primera fuente anual, así que el núcleo gana `frequency: 1y`. Cada valor va fechado el 1 de enero a medianoche
de Madrid, y la regla de huecos cuenta los 1 de enero que caen en la ventana, igual que `1mo` cuenta meses.

- **`lag_days: 350`**: el INE publica las cifras a 1 de enero de un año a mediados de diciembre de ese mismo año. La
  ventana acaba 350 días antes de ayer, así que el año en curso entra a partir de diciembre.
- **`min_days: 1095`**: cada ejecución relee los tres últimos años, porque el INE revisa las cifras una vez después
  de publicarlas.
- **`max_days: 11500`**: el histórico desde 1996 cabe en un único run de backfill.

## Límites municipales

El seed `dim_municipalities` guarda el código, el nombre, el centro, la superficie y el límite de cada municipio.

- Salen de los límites municipales del IGN que publica `es-atlas` 0.6.0 (TopoJSON con los códigos INE), filtrados a
  los municipios con el centro en Mallorca. Palma incluye el archipiélago de Cabrera.
- Se simplificaron a unos 150 m para los mapas de la web. La superficie (3.649 km² en total) se calculó con los
  límites completos.
- Se escribieron una vez: los límites solo cambian cuando un municipio se segrega, y el último fue Ariany, en 1982.

## Lo que enseñaron las pruebas reales (2026-11-05)

- **El backfill de 1996 a 2025 son 4.611 filas**: 53 municipios × 29 años × 3 métricas. La regla de huecos marca un
  año sin dato por municipio y métrica, que es 1997. Es correcto, porque ese año no hubo padrón.
- **El calendario de dbt empezaba en 2002**, con el histórico de calidad del aire. `agg_daily_metrics` comprueba cada
  día contra `dim_date`, así que los padrones de 1996 a 2001 rompían la relación. Ahora `dim_date` empieza en 1996.
- **La población de Mallorca a 1 de enero de 2025 es de 960.270 habitantes** (+1,2 % en un año). Palma tiene
  434.786.

## Servicio por habitante

La web asigna cada parada de EMT y CTM a su municipio: el límite que la contiene o, para las pocas paradas de costa
que el límite simplificado deja fuera, el municipio con el centro más cercano. Con eso calcula los pasos programados
por cada 1.000 habitantes. En un día laborable de noviembre de 2026, Palma tiene 186, Calvià 121 y Manacor 27.
