# 0023 · Caché y límite de peticiones en la memoria de cada proceso de la API

- **Estado:** Aceptada
- **Fecha:** 2026-11-14

## Contexto

La web pide los mismos marts mensuales y anuales en cada visita: reservas, clima, turismo, recursos, población y
los límites municipales. El DAG los reconstruye una vez al día, así que repetir la consulta en cada visita no aporta
nada. Los municipios son el caso más pesado: sus polígonos tardan más en serializarse que en consultarse.

La API es pública y de solo lectura. Un cliente desbocado (un script en bucle, una pestaña que reintenta sin
pausa) podía ocupar el pool de cinco conexiones y dejar sin servicio a la web.

La API corre en una máquina, con dos workers de uvicorn detrás del nginx de la web.

## Decisión

- **Caché de respuestas** en un middleware ASGI propio (`api/middleware.py`). Guarda durante una hora
  (`API_CACHE_SECONDS`) las respuestas 200 de los marts que se reconstruyen una vez al día. La clave es la ruta más
  los parámetros ordenados. Cada respuesta lleva un `ETag`, y con `If-None-Match` contesta 304 sin cuerpo.
  `Cache-Control: max-age` dice a navegadores y proxies cuánto le queda a la entrada. Tiene como mucho 256
  entradas y descarta la menos usada.
- **Límite por cliente**: un *token bucket* de 300 peticiones por minuto (`API_RATE_LIMIT_PER_MINUTE`), con ráfagas
  de hasta 300. Por encima contesta 429 con `Retry-After`. Todas las respuestas llevan `RateLimit-Limit` y
  `RateLimit-Remaining`. `/v1/health` no cuenta, porque es el healthcheck de Docker.
- El cliente es la dirección que ve uvicorn. `FORWARDED_ALLOW_IPS` limita a las redes privadas los proxies de los
  que acepta `X-Forwarded-For`. Así, cada visitante de la web cuenta por separado, y no todos como el nginx.
- Los dos viven en la memoria de cada worker, sin un almacén compartido.

## Alternativas descartadas

- **Redis para la caché y los contadores.** Sería un servicio más que arrancar, vigilar y versionar, para unos
  datos que cambian una vez al día y un límite que solo debe frenar abusos. Es el mismo razonamiento que la
  [ADR 0018](0018-sin-cache-de-extraccion.md).
- **Caché en nginx (`proxy_cache`).** Solo cubriría a quien entra por la web: no a quien llama a la API directamente
  en el puerto 8000. Además, la lista de rutas cacheables quedaría lejos del código que sabe qué cambia a diario.
- **Librerías (`slowapi`, `fastapi-cache`).** Unas 150 líneas propias, con su test, no justifican una dependencia
  más en la imagen pequeña de la API. Además, ninguna de las dos da el 304 con `ETag` tal cual.
- **Invalidar la caché al terminar dbt.** Haría falta un aviso del DAG a la API, o una consulta de frescura en cada
  petición. Con una hora de TTL, un dato nuevo tarda como mucho una hora en verse, y eso basta para series mensuales.

## Consecuencias

- **A favor.**
  - La segunda visita a un mart no toca el warehouse.
  - Un navegador que ya tiene la respuesta recibe un 304 vacío.
  - Ningún cliente puede acaparar el pool de conexiones.
- **En contra.**
  - Cada worker tiene su caché y sus contadores. Con dos workers, una entrada puede consultarse dos veces, y el
    límite real llega a 600 por minuto si las peticiones se reparten.
  - Un reinicio vacía las dos cosas.
  - Tras el dbt diario, un mart puede servirse con hasta una hora de retraso.
  - Si alguien llama directamente al puerto publicado desde la propia máquina, entra por la puerta de enlace de
    Docker, que está en una red privada. Podría falsear `X-Forwarded-For` para saltarse el límite. Es aceptable en
    local; en un despliegue público, la API no publicaría su puerto.

## Cuándo revisarla

Habría que revisarla en cualquiera de estos casos:

- La API pasa a varias máquinas, o a más de unos pocos workers. Los contadores repartidos dejarían de significar algo.
- Un mart empieza a cambiar más de una vez al día.
- El límite tiene que cobrar o garantizar un cupo, y no solo frenar abusos.

Entonces, Redis o la caché y el límite del API Gateway de la nube.
