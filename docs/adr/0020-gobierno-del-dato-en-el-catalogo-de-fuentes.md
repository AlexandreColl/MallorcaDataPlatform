# 0020 · El gobierno del dato vive en el catálogo de fuentes, con un SLA por fuente

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto

La plataforma lee 15 fuentes de 13 organismos. Hasta ahora no estaba escrito en ninguna parte quién es el dueño de
cada dato, con qué licencia se usa ni si tiene datos personales. Tampoco qué servicio se espera de cada fuente.

Lo que había eran umbrales fijos repartidos por varios sitios:

- 36 h sin una carga correcta en la web y en Grafana;
- más de 800 días de antigüedad para tratar una fuente como histórico en la web;
- un umbral de frescura por fuente en `_sources.yml`.

Ninguno decía si una fuente mensual con datos de hace dos meses estaba bien o mal.

## Decisión

- **La ficha de gobierno es parte del catálogo de fuentes** (`dbt/seeds/dim_sources.csv`), la misma fila que ya
  tenía la etiqueta y el tipo de cada fuente:
  - dominio, dueño, licencia y enlace a sus condiciones;
  - acceso;
  - datos personales y clasificación;
  - ciclo de vida;
  - el SLA: antigüedad máxima del último dato y parte mínima de cargas correctas en 7 días.
- **Los tests de dbt la hacen obligatoria:** campos no nulos, listas de valores cerradas y rangos.
- **`gold.source_health` evalúa el SLA:** `sla_age_met`, `sla_success_met` y `sla_met`. La API lo sirve anidado en
  `governance` y `sla`.
- **La web y Grafana leen el SLA de la ficha en lugar de umbrales propios:**
  - un estado *Fuera de SLA*;
  - un panel de gobierno;
  - una alerta *Fuente fuera de su SLA*;
  - el ciclo de vida sustituye a la regla de los 800 días.
- **Donde un dueño no publica licencia, la ficha lo dice** y no se inventa una.

## Alternativas descartadas

- **Un bloque `governance` en cada `connector.yaml`.** El dato está junto al código del conector, pero dbt no lee
  esos YAML. Habría que copiarlo al warehouse en cada ejecución del pipeline, o generar el seed con un script. El
  seed ya era la ficha de cada fuente en gold y ya tenía un test que exige una fila por fuente.
- **Un catálogo de datos (DataHub, OpenMetadata).** Son la herramienta adecuada con cientos de tablas y varios
  equipos. Aquí añadirían un servicio pesado (Elasticsearch, Kafka o MySQL) para 15 filas. El linaje ya lo cubre
  Marquez ([ADR 0017](0017-observabilidad-y-linaje.md)).
- **Derivar el SLA de lo observado** (por ejemplo, el percentil 95 de la antigüedad). Un SLA es un compromiso, no
  una medida: si se deriva de lo que pasa, nunca se incumple.

## Consecuencias

- **A favor.**
  - Cada pregunta de gobierno tiene una respuesta en un sitio, revisada en un PR y servida por la API.
  - La alerta y la web juzgan cada fuente según su cadencia: Dataestur con 70 días ya no parece rota, y AEMET con 7
    días sí lo parece.
- **En contra.**
  - La alerta del SLA lee un mart de dbt (`gold.source_health`), cuando las demás alertas leen solo tablas
    operativas. Se mitiga calculando la antigüedad en vivo: el último dato solo cambia con una carga y su build.
    Además, la alerta de 36 h sin carga correcta sigue leyendo `ops.ingestion_runs`.
  - Los umbrales de `dbt source freshness` siguen en `_sources.yml`, porque el YAML no puede leer el seed. Miden
    algo distinto: si las cargas traen filas nuevas, no la antigüedad del dato. Desde la v0.15.0, su `error_after` es
    el SLA del catálogo y un test (`tests/test_freshness_sla.py`) falla si se separan.

## Cuándo revisarla

- **Más de un equipo publica o consume datos.** Haría falta un catálogo con búsqueda, dueños con nombre y
  permisos: OpenMetadata, que también lee los manifest de dbt.
- **Llega una fuente con datos personales.** Habría que decidir la clasificación por columna y un rol de lectura
  aparte, no solo marcar la fuente.
