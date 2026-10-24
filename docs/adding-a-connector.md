# Añadir un conector (objetivo: ≤ 1 día)

1. **Probar la API a mano** y anotar en un issue (`Nuevo conector`): URL, autenticación, frecuencia,
   cobertura en Mallorca, ejemplo de respuesta.
2. Rama: `git switch develop && git switch -c feature/connector-<nombre>`.
3. Crear la carpeta:

```
connectors/<nombre>/
├── __init__.py
├── connector.yaml        # datasets, métricas, unidades, rangos válidos, secretos
├── extractor.py          # clase que hereda de BaseConnector
├── README.md             # qué datos trae y sus limitaciones
└── tests/
    ├── fixtures/*.json   # respuestas REALES grabadas con curl
    └── test_<nombre>.py
```

4. `connector.yaml`: el campo `name` debe coincidir con la carpeta. `frequency` alimenta la regla de
   huecos (`1h`, `1d`…); si los datasets tienen granularidades distintas, cada uno puede declarar la suya
   (`datasets.<x>.frequency`, ver `connectors/redata`). `secrets` lista las variables que deben estar en `.env`.
   Si la API limita el rango por petición, trocea con `window.split(max_days)` y genera un payload por trozo.
5. `extractor.py` implementa dos métodos:
   - `extract(window, region) -> list[RawPayload]`: llama a la API y devuelve la respuesta **sin tocar**.
   - `normalize(payload, region) -> Iterable[Observation]`: convierte al esquema común.
     Filtra por `region.contains(lat, lon)` si la fuente es de puntos (estaciones, boyas).
   - Si la fuente trae su propio control de calidad, emite `quality="suspect"` en las observaciones dudosas: la
     regla `source_qc` lo conserva y lo cuenta (ver `connectors/socib`).
   - Si un dataset se pide en varias peticiones por ventana (una por estación…), usa `RawPayload(partition=...)`
     para que cada respuesta tenga su propio objeto en bronze.
   - Para respuestas que no son JSON (CSV, XML) usa `self.http.get_text`.
6. Tests contra las fixtures (sin red). Ver `connectors/open_meteo/tests/` como plantilla.
7. Probar de punta a punta: `make run CONNECTORS=<nombre> DAYS=1` y mirar Grafana.
8. Sección en el README, entrada en `CHANGELOG.md` → PR `✨ feat(connector): add <nombre>`.

No hace falta tocar el núcleo, el DAG ni dbt: el registro descubre el conector, el DAG lo ofrece como
parámetro y los modelos gold lo incluyen automáticamente.
