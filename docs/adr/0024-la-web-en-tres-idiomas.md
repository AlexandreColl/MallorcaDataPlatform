# 0024 · La web en castellano, catalán e inglés, con el idioma en la URL y sin librería

- **Estado:** Aceptada
- **Fecha:** 2026-11-17

## Contexto

La web estaba solo en castellano. En Mallorca se habla castellano y catalán, y la web es también un proyecto de
portafolio que se lee desde fuera. Tiene unos 250 textos en siete páginas y catorce componentes, y formatea números y
fechas en `lib/format.ts` con los meses escritos a mano.

Esos formatos no solo se usan en los componentes de React: también los llaman los tooltips y los ejes de ECharts y
las fichas de los mapas, que se pintan fuera del árbol de React.

## Decisión

- **Tres idiomas:** castellano (`es-ES`), catalán estándar (`ca-ES`) e inglés británico (`en-GB`).
- **El idioma va en la URL:** `/es/movilidad`, `/ca/movilidad`, `/en/movilidad`. Las rutas no se traducen.
  - Una dirección sin idioma, como un enlace antiguo o el dominio a secas, se reescribe con `replaceState` en el idioma
    elegido antes con el selector o, si no hay ninguno, en el primero de los del navegador que la web habla.
    Si tampoco hay ninguno, en castellano.
  - Un enlace con idioma manda siempre: un enlace compartido se abre en el idioma en que se envió.
- **Los textos están en diccionarios tipados**, uno por idioma, en `web/src/i18n`.
  - `es.ts` es la referencia, y su forma es el tipo de los otros dos: si falta un texto o sobra uno, `tsc` falla.
  - Los textos con datos son funciones, como `loadError(error)`, así que TypeScript comprueba también sus parámetros.
  - Los tres diccionarios van en el bundle porque son pequeños.
- **Los números y las fechas se formatean con `Intl`**: `NumberFormat`, `DateTimeFormat` y `RelativeTimeFormat`, en
  lugar de tablas de meses.
- **El idioma es fijo durante una carga de la página.** El selector enlaza la misma página, con sus filtros, en otro
  idioma, y cambiar de idioma vuelve a cargarla.
  - Por eso el idioma es un valor del módulo `i18n` y no un contexto de React. Los formatos que corren en ECharts y
    en los mapas lo leen igual que los componentes.
- **El selector** nombra cada idioma en su propia lengua (Castellano, Català, English). No usa banderas, porque una
  bandera es un país y no un idioma.
  - Cada idioma es un enlace con `lang` y `hreflang`.
  - `<html lang>` cambia con el idioma, para que el lector de pantalla y el corrector lean el texto correctamente.
- **Los textos del catálogo de fuentes** (etiqueta, descripción y licencia) están en el seed `dim_source_texts`.
  - Hay una fila por fuente e idioma, así que añadir un idioma añade filas, no columnas.
  - El castellano sigue en `dim_sources`: es la referencia y el valor por defecto si falta una traducción.
  - Un test de dbt exige que cada fuente tenga sus textos en cada idioma.
- **La API elige el idioma por la cabecera `Accept-Language`** (`api/language.py`), con sus `q`, y responde
  con `Content-Language` y `Vary: Accept-Language`.
  - Solo cambian con el idioma las respuestas que llevan textos del catálogo: `/v1/sources`, `/v1/locations` y
    `/v1/weather/daily`.
  - La caché de la API guarda una respuesta por idioma en las rutas cuya respuesta dice `Vary: Accept-Language`, y
    cada una tiene su `ETag`.
  - La web manda el idioma de la página en cada petición.
- **Los nombres propios no se traducen**: estaciones, municipios, paradas, zonas de aviso de AEMET, acuíferos y
  dueños de los datos.

## Alternativas descartadas

- **react-i18next o react-intl.** Con 250 textos y tres idiomas añaden una dependencia y un formato de mensajes
  (ICU o JSON) cuyas claves son texto sin comprobar si no se configura aparte. Además, necesitan su contexto en cada
  formateador que corre fuera de React. La web ya evitó una dependencia por la misma razón con el router.
- **El idioma solo en `localStorage`.** Un enlace compartido se abriría en el idioma de quien lo recibe, no de quien lo
  envía. Además, las capturas de cada idioma no se podrían pedir por dirección.
- **Castellano sin prefijo y los otros con prefijo.** `/movilidad` no distinguiría "castellano elegido" de "sin
  elegir", y no se sabría si respetar la preferencia guardada.
- **Una columna por idioma en `dim_sources`** (`label_ca`, `label_en`...). Cada idioma nuevo cambiaría el
  seed, su contrato y cada consulta que lee el catálogo.
- **El idioma en un parámetro `?lang=`.** Es la cabecera que el navegador ya manda, y la que las cachés HTTP
  saben distinguir con `Vary`.
- **Traducir las etiquetas en la web por el código de la fuente.** Duplicaría el catálogo en dos sitios, y Grafana,
  la documentación de dbt o cualquier otro cliente de la API no lo verían.
- **Cambiar de idioma sin recargar.** Obligaría a pasar el idioma a cada formateador de ECharts y de los mapas, o a
  volver a montar el árbol. Recargar cuesta volver a pedir los datos, que la API sirve desde su caché
  ([ADR 0023](0023-cache-y-limite-en-el-proceso-de-la-api.md)), y se cambia de idioma pocas veces.

## Consecuencias

- **A favor.** Un texto que falta en un idioma no compila. Los enlaces conservan el idioma. Las fechas siguen las
  reglas de cada lengua, como "4 d’ag." o "4 Aug", sin escribirlas a mano.
- **En contra.** `Intl` depende de la versión de ICU del navegador: un punto o un espacio puede variar entre
  navegadores. Los tests fijan lo que escribe el ICU de Node 26, la misma versión que usan CI y la imagen.
- **En contra.** Una fuente nueva necesita sus textos en tres idiomas; el test de dbt lo recuerda. Grafana sigue en
  castellano.

## Cuándo revisarla

Si la web pasa de unos 1.000 textos, si hacen falta plurales que no son "uno u otros" (otro idioma) o si las
traducciones las va a hacer alguien fuera del código. En ese caso, conviene una librería con mensajes ICU y ficheros
que una herramienta de traducción pueda leer.
