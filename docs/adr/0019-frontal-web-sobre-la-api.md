# 0019 · Un frontal web propio que solo lee la API

- **Estado:** Aceptada
- **Fecha:** 2026-11-05

## Contexto

Grafana enseña bien los datos a quien opera la plataforma: series, alertas y estado de las cargas. Pero a quien
solo quiere saber cómo está la isla le enseña paneles densos, con un aspecto de herramienta interna. El proyecto
necesitaba una portada que se entienda en 30 segundos: unas pocas cifras, si son normales o no, y dónde se mide.

## Decisión

- Un frontal en `web/` con React, TypeScript y Vite. Usa ECharts para los gráficos y MapLibre con teselas de
  OpenStreetMap para el mapa.
- La primera página tiene tres partes:
  - **Cinco cifras clave:** reservas de agua, lluvia del año hidrológico, turistas, demanda eléctrica y temperatura.
    Cada una muestra su último mes, su desviación frente a lo normal para ese mes y los últimos 36 meses.
  - **Un mapa** con las estaciones, los puntos de modelo y las paradas.
  - **El estado de cada fuente.**
- **Solo lee la API REST, nunca el warehouse.** Para el mapa se añadió `GET /v1/locations`, que sale de
  `dim_locations` y `dim_sources`.
- Se sirve con nginx en su propio servicio de Compose (puerto 3002), que además hace de proxy de `/api` hacia la
  API. Así el navegador solo habla con un origen.
- **Grafana se queda para operar la plataforma:** alertas, calidad, anomalías y correcciones. La web no lo
  sustituye.

## Alternativas descartadas

- **Rehacer los dashboards de Grafana.** Su aspecto sigue siendo el de una herramienta interna, y el diseño está
  limitado por sus paneles.
- **Streamlit o Superset.** Hacen falta Python o un servicio pesado más, y el resultado sigue pareciendo una
  herramienta de análisis, no una portada.
- **Observable Framework o Evidence.** Son muy vistosos y piden poco código, pero generan un sitio estático: los
  datos se quedan congelados en cada build y habría que leer el warehouse durante la construcción.
- **Que la web lea Postgres directamente.** Se saltaría los contratos de la API y añadiría otra credencial al
  warehouse.

## Consecuencias

- **A favor.**
  - La API pasa a tener un consumidor real, y su contrato se ejercita en cada visita.
  - El exposure `web_home` de dbt dice qué marts rompería un cambio.
  - La web es estática: nginx la sirve sin estado, y escala y se despliega sola (por ejemplo, en S3 con CloudFront).
- **En contra.**
  - Una pila más que mantener: Node, sus dependencias y un job de CI.
  - El mapa depende de las teselas públicas de OpenStreetMap. Su política de uso pide poco tráfico y la
    atribución, y basta para una demo, pero no para tráfico real.

## Cuándo revisarla

- Si la web crece a varias páginas, harán falta un router y una caché de datos (React Router y TanStack Query).
- Si la web tiene tráfico real, harán falta un proveedor de teselas con clave o teselas propias (PMTiles en S3).
