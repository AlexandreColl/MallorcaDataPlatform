# 0007 · Calidad de ingeniería y entrega

- **Estado:** Aceptada
- **Fecha:** 2026-10-24

## Contexto

El proyecto lo mantiene una sola persona y depende de APIs ajenas que cambian sin avisar. Los tests unitarios no
detectan que una fuente cambie; un E2E contra las APIs reales sí, pero es lento y depende de terceros.

## Decisión

- **Conectores.** Se prueban con respuestas reales grabadas, así que los tests son deterministas y rápidos.
- **Cobertura.** `core/` exige un mínimo del 80 %, contando ramas.
- **CI en cada PR:**
  - ruff con todas las reglas;
  - pytest con PySpark;
  - integridad del DAG;
  - `dbt build` sobre un Postgres vacío, con slim CI;
  - las escrituras del warehouse contra Postgres;
  - Terraform contra un proveedor simulado.
- **E2E.** Levanta la pila y ejecuta el DAG dos veces contra las APIs reales, en los PR a `main` y una vez por
  semana.
- **Ramas y releases.**
  - Git flow con `develop` y `main` protegidas.
  - Títulos con gitmoji y Conventional Commits.
  - Una release por tag, con imágenes en GHCR.

## Alternativas descartadas

- **Solo tests unitarios.** No habrían visto que SOCIB movió su servicio a `/ncss/point/`; el E2E semanal sí lo vio.
- **E2E en cada PR.** Tardaría demasiado, y el CI fallaría cada vez que una API ajena estuviera caída.

## Consecuencias

- **A favor.** Un cambio en una fuente se detecta en una semana como mucho. Un cambio en el código se detecta en el
  PR.
- **En contra.** El E2E depende de terceros. Por eso distingue un corte de la fuente, que es un aviso, de un fallo
  propio, que es un error.

## Cuándo revisarla

Si el E2E da falsos rojos a menudo. Entonces habría que grabar también las respuestas del E2E y dejar las APIs reales
solo para una comprobación de contrato aparte.
