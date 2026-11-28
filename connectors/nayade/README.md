# Náyade (calidad de las aguas de baño)

- **Fuente**: [Náyade](https://nayadeciudadano.sanidad.gob.es/Splayas/ciudadano/ciudadanoZonaAction.do), el Sistema
  de Información Nacional de Aguas de Baño del Ministerio de Sanidad. Las comunidades autónomas cargan en él cada
  muestra que toman en temporada; en Baleares, la Conselleria de Salut (los análisis de Mallorca los hace el
  Laboratorio de Salud Pública de Palma).
  - No tiene API ni descarga: es una aplicación web de formularios (Struts, HTML en latin1). Tres páginas responden a
    un GET sin sesión y bastan:
    - `ciudadanoListaZonaAction.do?codCCAA=4&codProvincia=7&codMunicipio=<código INE sin el cero>`: las aguas de baño
      de un municipio, cada una con un enlace `verZona('<id>')`;
    - `ciudadanoVerZonaAction.do?codZona=<id>&pestanya=1`: el agua de baño (nombre, isla, temporada) y sus puntos de
      muestreo, cada uno con sus coordenadas UTM (ETRS89, huso 31);
    - la misma página con `pestanya=3`: por punto de muestreo, cada muestra de las cuatro últimas temporadas (fecha,
      *E. coli*, enterococos intestinales y el aviso que la acompaña) y los «incidentes» (restricciones del baño, con
      su día de apertura y de cierre y la medida).
- **Licencia**: el [aviso legal](https://www.sanidad.gob.es/avisoLegal/home.htm) del Ministerio de Sanidad autoriza
  la reutilización de la información de su web para usos comerciales y no comerciales (Ley 37/2007), sin
  desnaturalizarla, citando la fuente y la fecha de la última actualización.
- **Autenticación**: ninguna.
- **Datos**: 87 aguas de baño de Mallorca en 18 municipios (temporada 2026), con 113 puntos de muestreo, desde la
  temporada 2023.

| Métrica | Origen | Unidad |
|---|---|---|
| `e_coli` | Columna *Escherichia coli* de cada muestra | `cfu/100ml` |
| `enterococci` | Columna *Enterococo* | `cfu/100ml` |
| `bathing_advice` | Observación de la muestra: 0 apta para el baño, 1 recomendación de no baño, 2 baño prohibido temporalmente | `level` |
| `incident_days` | Días entre la apertura y el cierre de una restricción, en su día de apertura | `days` |
| `incident_level` | Medida de la restricción: 1 recomendación de no baño, 2 prohibición | `level` |

La `entity` es el punto de muestreo, `<municipio>_<agua de baño>_<punto>` (`07040_1033_PM3`): un agua de baño puede
tener hasta seis puntos, y el código INE del municipio en el identificador la une con `dim_municipalities` en gold.
El nombre (en `silver.entities`) es el del agua de baño, con el punto entre paréntesis si tiene varios
(«Playa de Palma (PM3)»), y `lat`/`lon` las del punto, pasadas de UTM a grados con las fórmulas de Snyder (la imagen
no trae pyproj; a escala de una playa ETRS89 y WGS84 son lo mismo). Cada valor va fechado el día de la muestra a
medianoche de Madrid. Náyade da casi todos los resultados en NMP/100 ml y algunos en UFC/100 ml; la directiva
2006/7/CE trata las dos unidades igual, y el 10 es el límite de detección del método (se escribe 10 cuando no se
encuentra nada).

## Bronze: las páginas, sin el menú

Un solo payload por ejecución (`bathing_waters`) con, por agua de baño, su municipio, su id y las dos páginas desde
sus pestañas: lo de encima (scripts y menús) es igual en todas las páginas. Las dos tablas (muestras e incidentes)
salen de la misma página, así que van en un mismo dataset y bronze no guarda dos veces el cuerpo.

## Temporada: eventos, no una serie con huecos

Se muestrea más o menos cada dos semanas de abril a septiembre (la temporada de 2026 fue del 4 de mayo al 2 de
octubre, más una muestra previa en abril) y nada en invierno. El dataset es `frequency: event`: sin regla de huecos,
siete meses sin muestras no son siete meses de datos que faltan, y una ventana sin muestras es un resultado válido y
vacío. Un resultado o un aviso que Náyade deja en blanco no se reportó: no se guarda fila, no un nulo. El SLA de
antigüedad del catálogo es de 240 días (de la última muestra de septiembre a la primera de abril o mayo).

## Ventana

Náyade solo enseña las cuatro últimas temporadas (justo el periodo con el que se calcula la clasificación europea) y
siempre entera, sea cual sea la ventana: `extract` pide todo y `normalize` filtra por la ventana. Cada ejecución
relee los últimos 400 días (`min_days`), así que una muestra cargada tarde o corregida entra al día siguiente.
`max_days` es 1.500 para el backfill de las cuatro temporadas. Cada ejecución son 53 listas de municipio y dos
páginas por agua de baño (unas 230 peticiones, 15 segundos).

## En gold, la API, la web y Grafana

- `fct_bathing_water_seasons`: un agua de baño y temporada, con sus muestras, los peores resultados, los avisos y las
  restricciones, y la **clase de la directiva 2006/7/CE** (anexo II, aguas costeras) calculada con las muestras de
  esa temporada y las tres anteriores: percentiles 95 y 90 de los logaritmos (10^(media + 1,65·σ) y
  10^(media + 1,282·σ)) de *E. coli* y enterococos; 4 excelente (P95 ≤ 250 y ≤ 100 ufc/100 ml), 3 buena (P95 ≤ 500 y
  ≤ 200), 2 suficiente (P90 ≤ 500 y ≤ 185), 1 insuficiente. Sin clase con menos de 16 muestras o con una sola
  temporada. También la clase de la temporada anterior y el cambio.
- `fct_bathing_water_island_yearly`: la isla por temporada, cuántas aguas hay en cada clase y el porcentaje de
  excelentes entre las clasificadas.
- API: `GET /v1/water/bathing` (cada agua de baño en una temporada, por defecto la última, peores primero) y
  `GET /v1/water/bathing/island`.
- Web, Clima y agua: el mapa de las playas con el color de su clase (con la ficha de cada una al pulsarla) y las
  playas de cada clase por temporada con el porcentaje de excelentes.
- Grafana, Clima y agua: el mapa de la última temporada del rango (panel 15) y las clases por temporada (panel 16).

Es una **reproducción del método, no la clasificación oficial**: el agua de baño suma las muestras de todos sus
puntos, y la evaluación oficial puede descartar las muestras tomadas durante una contaminación de corta duración.

## Lo que enseñaron las pruebas reales (2026-11-28)

- **La EEA no respondía.** El servicio SQL de DiscoData (`discodata.eea.europa.eu`) devolvió 502 en todas las
  consultas, incluso en la raíz, por segundo día, y el catálogo y las descargas de `sdi.eea.europa.eu` no aceptaban
  conexiones (ni desde Windows ni desde WSL ni desde WebFetch). La ficha del Datahub sí carga: el conjunto vigente es
  *Bathing Water Directive - Status of bathing water, 2025 v1.0*, un xlsx con la clasificación oficial de 1990 a
  2025. Queda para un PR aparte cuando vuelva; Náyade no trae el identificador europeo del agua de baño, así que
  habrá que emparejarlas por coordenadas.
- **Ni la CAIB ni datos.gob.es tienen las muestras.** El Govern publica un informe anual en PDF (2010-2024) y el
  mapa de su web de playas es de seguridad, no de calidad del agua. En datos.gob.es solo está el censo anual de
  zonas de baño (cartografía); el WMS del censo de 2025 del MITECO falla (`NullReferenceException` de ArcGIS).
- **Náyade responde sin sesión.** Recorrer el formulario parecía exigir la cookie, pero la lista de un municipio y
  las pestañas de un agua de baño contestan a un GET directo con sus parámetros.
- **Cuatro temporadas, no más.** Las muestras van de abril de 2023 a septiembre de 2026 (1.017 días de muestra por
  punto en cada temporada, 1.018 en 2025); la serie a partir de ahora la acumula la plataforma. Los incidentes solo aparecen los de la
  temporada en curso: 44 restricciones en 2026 (10 de ellas prohibiciones, 102 días en total) y ninguna antes,
  aunque sí hay muestras con aviso de no baño en 2023-2025.
- **Varios puntos por agua de baño.** 73 aguas tienen un punto, 7 dos, 4 tres, 2 cuatro y Playa de Palma seis (PM1 y
  de PM3 a PM7, sin PM2). Por eso la entidad es el punto y gold agrega por agua de baño.
- **Una muestra que repite el día.** Un punto puede tener dos filas el mismo día (la repetición tras un mal
  resultado); se queda el peor valor de cada métrica, porque silver tiene un valor por serie y día. Las filas de
  incidentes también llevan una fecha en la primera columna, así que el parser separa las dos tablas por su título
  («Muestreos:» e «Incidentes:»), no por la forma de la fila.
- **Avisos.** Tres textos: «Zona Apta para el baño» (4.025 días de muestra), «Recomendación de no baño» (29) y «Zona
  donde queda prohibido el baño temporalmente» (15). Uno nuevo hace fallar `normalize` en vez de perderse.
- **Nombres.** Náyade los escribe en mayúsculas y a veces con el paréntesis pegado («LLENAIRE(PORT DE POLLENÇA)»); el
  conector los pasa a «Playa Llenaire (Port de Pollença)».
- **Un artefacto de los puntos.** Con la primera regla (16 muestras) se clasificaban 14 aguas en 2023 solo por tener
  varios puntos (9 muestras por punto y temporada); con la segunda condición (dos temporadas por lo menos) 2023 queda
  sin clasificar, como debe.
- **Backfill.** 2023-01-01 a 2026-11-27 en una ejecución: 12.295 valores, 113 nombres de punto, 0 reglas de calidad
  fallidas. En gold, el porcentaje de aguas excelentes sube de 73,6 % (2024) a 75,9 % (2025) y 79,3 % (2026: 69
  excelentes, 16 buenas, 1 suficiente y 1 insuficiente, Cala Egos en Santanyí, con un P95 de *E. coli* de 1.765).
  El peor resultado de las cuatro temporadas: 17.329 *E. coli* por 100 ml, también en Cala Egos, en 2024.

## Grabar las fixtures

Grabar la isla entera son 53 listas y dos páginas por agua de baño (unos 3 MB), así que las fixtures guardan solo
Pollença (seis aguas de baño: una con un punto, dos con tres puntos y las restricciones de agosto de 2026 en
Tamarells, 350 KB). Se graban con un script que carga el conector con ese municipio solo y un `Recorder`
(`core.connectors.recording`) en vez de `make record-fixtures`, y los tests cargan el conector igual.
