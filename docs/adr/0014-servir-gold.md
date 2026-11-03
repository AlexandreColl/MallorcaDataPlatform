# 0014 · Servir gold: Grafana como código y una API pequeña

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Gold tiene dos tipos de consumidor: una persona que mira series, mapas y alertas, y un programa que pide datos.
Ninguno de los dos debe poder escribir, y un cambio en gold no debe romper a ninguno sin avisar.

## Decisión

- **Grafana.**
  - Seis dashboards y tres alertas, provisionados desde ficheros JSON y YAML.
  - Un exposure de dbt por dashboard.
- **API.**
  - FastAPI de solo lectura, en su propia imagen, sin Airflow, Spark ni Java.
  - Las consultas tienen un límite de 15 s.
- **Acceso.**
  - Cada consumidor tiene su propio rol de Postgres de solo lectura.
  - Las claves van en un `.env` fuera del repositorio.

## Alternativas descartadas

- **Streamlit o Superset como visor principal.** Grafana ya trae alertas, mapas y anotaciones (las anomalías se
  dibujan sobre las series), y se provisiona entero desde ficheros.
- **Que la API lea `silver.observations`.** Se saltaría los contratos de gold. La única tabla de silver que lee es
  `silver.anomalies`, porque no tiene un equivalente en gold.

## Consecuencias

- **A favor.**
  - Los dashboards se revisan en los PR como cualquier otro código.
  - Los exposures dicen qué consumidor rompería un cambio.
  - La API se despliega y escala por separado.
- **En contra.** Grafana como código obliga a editar JSON a mano, o a exportarlo desde la interfaz y revisar el
  diff.

## Cuándo revisarla

Si aparecen usuarios que exploran sin saber SQL. Entonces haría falta una herramienta de BI con capa semántica
encima de los mismos marts.
