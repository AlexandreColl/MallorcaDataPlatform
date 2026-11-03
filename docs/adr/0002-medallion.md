# 0002 · Medallion: bronze crudo, silver común, gold con dbt

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

Las fuentes cambian de formato, revisan datos ya publicados y a veces desaparecen. Por ejemplo, el histórico de
calidad del aire del Govern acaba en 2021. Si solo se guarda el resultado transformado, cada cambio obliga a
descargar de nuevo, y eso a veces ya no es posible.

## Decisión

Tres capas:

- **Bronze** guarda la respuesta tal cual llegó, con una clave determinista
  (`<fuente>/<dataset>/window=<desde>_<hasta>/payload.json`), en un bucket versionado.
- **Silver** es el esquema común ([0001](0001-nucleo-fijo-y-conectores.md)), con la calidad marcada. Vive en el lake
  y en Postgres.
- **Gold** son los modelos de dbt pensados para consultar.

## Alternativas descartadas

- **Cargar directamente en Postgres.** Se pierde el crudo, y cada cambio de formato obliga a volver a llamar a la
  fuente.

## Consecuencias

- **A favor.**
  - Se puede reprocesar sin volver a llamar a la fuente.
  - Con el versionado, una revisión de la fuente nunca borra lo que dijo antes.
  - Silver separa la limpieza (Python y Spark) del modelado (SQL con dbt).
- **En contra.**
  - Silver está dos veces, en el lake y en Postgres: 2,6 GB repetidos.
  - La doble escritura ocurre en la misma tarea, y las dos copias usan la misma clave.

## Cuándo revisarla

Cuando el warehouse pase a un motor que lea el lake directamente (Athena sobre Delta). Entonces la copia de silver
en Postgres sobra, y Postgres queda solo para servir marts pequeños.
