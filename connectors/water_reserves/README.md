# Reservas hídricas de Mallorca (Govern de les Illes Balears)

- **Fuente**: Portal del Agua de la Direcció General de Recursos Hídrics,
  [Evolución de las reservas hídricas e índice de sequía](https://www.caib.es/sites/aigua/es/evolucion_de_las_reservas_hidricas_e_indice_de_sequia-22867/).
  Se actualiza cada mes, con unos dos meses de retraso (agosto se publicó a finales de octubre).
- **Autenticación**: ninguna.
- **Datos**: reservas de agua subterránea como porcentaje de un acuífero lleno, mensuales.

| Métrica | Unidad | Entidades |
|---|---|---|
| `water_reserves` | % | `mallorca` (media ponderada de la isla) y `aquifer_<código>` (las 18 masas de agua subterránea, p. ej. `aquifer_1805m1`, Pollença) |

Los nombres y la unidad hidrogeológica de cada acuífero están en el seed `dim_aquifers`. `ts` es el día 1 del mes a
medianoche local (Europe/Madrid).

## Cómo funciona

La página publica cada mes ficheros nuevos, con otro nombre (`Reservas_Hidricas_2026_08_cast.ods`) y otro id, así que
`extract` lee la página y los busca por el texto del enlace (`link_text` en el YAML). Comprueba que cada fichero sea
lo que se espera (zip o `%PDF`), no una página de error, y lo guarda **sin tocar** en bronze.

| Dataset | Fichero | Qué aporta |
|---|---|---|
| `last_year` | hoja de cálculo ODS | los últimos 13 meses de cada acuífero y de la isla, con dos decimales; se lee con la librería estándar (un ODS es un zip de XML) |
| `history` | PDF «Evolución de las reservas hídricas ponderadas de Mallorca» | 10 años de la isla: las etiquetas de las barras del gráfico son texto (`pypdf`), en porcentajes enteros |

Del PDF solo se cargan los meses que la hoja de cálculo no tiene (`skip_last_months: 13`), así que donde coinciden
gana el valor más preciso. Las dos fuentes no siempre dicen lo mismo: de agosto de 2025 a febrero de 2026 la hoja
da entre 2 y 4 puntos más que el PDF (febrero: 59 % frente a 55 %); desde marzo coinciden.

Es mensual como Dataestur: `frequency: 1mo`, `min_days: 365` (cada ejecución relee el último año) y `lag_days: 62`.

## Limitaciones

- Los acuíferos solo tienen los últimos 13 meses: el histórico se irá acumulando en el warehouse. En un backfill
  largo (`--days 3650`) la regla de huecos cuenta como huecos los meses anteriores de cada acuífero.
- Las reservas son estacionales (máximo a final del invierno, mínimo a principio del otoño): un mes solo se compara
  con el mismo mes de otros años. Lo hace `fct_water_reserves_monthly` (`anomaly_pts`).
- El índice de sequía de la misma página solo se publica como gráfico, sin valores: no se carga.

Prueba real (2026-10-28):

- Ejecución por defecto: 228 filas (19 series × 12 meses) en 35 s, sin fallos de calidad.
- Diez años: 120 meses de la isla, de septiembre de 2016 a agosto de 2026.
- Agosto de 2026: 38 %, el agosto más bajo de los diez años (media de agosto, 49,5 %; anomalía de −11,5 puntos).
  7 de los 18 acuíferos están por debajo del 30 %; el más bajo es Son Real, con el 9 %.

Fixtures en `tests/fixtures/`: la página del portal y sus dos ficheros, tal como estaban el 2026-10-28.
