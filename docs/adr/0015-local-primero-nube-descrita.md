# 0015 · Local primero, nube descrita con Terraform

- **Estado:** Aceptada
- **Fecha:** 2026-10-30

## Contexto

El objetivo es demostrar el camino a AWS sin pagarlo. Además, la pila tiene que poder levantarla cualquiera con un
`docker compose up`.

## Decisión

- MinIO habla S3 y Spark usa S3A: pasar a AWS es cambiar el endpoint y las credenciales.
- `infra/terraform` describe la versión de AWS:
  - S3 privado, cifrado y solo con TLS, con versionado y ciclo de vida;
  - Glue Catalog leyendo la tabla Delta;
  - Athena con un límite por consulta;
  - IAM de mínimo privilegio;
  - un presupuesto de 2 USD.
- El CI lo valida con `fmt`, `validate`, tflint y `terraform test` contra un proveedor de AWS simulado.

## Alternativas descartadas

- **LocalStack.** Su edición gratuita no tiene Glue ni Athena.
- **Desplegar de forma permanente.** Cuesta dinero cada mes y deja una cuenta que mantener.

## Consecuencias

- **A favor.** Se prueba la intención sin cuenta y sin coste: los permisos, el cifrado, el ciclo de vida y que la
  tabla sea Delta.
- **En contra.**
  - Un proveedor simulado no prueba que AWS acepte la configuración.
  - Spark aún usa claves estáticas en lugar del rol.
  - Athena no hace *time travel* sobre Delta.

## Cuándo revisarla

Ya está prevista en el ROADMAP, en la fase 7: un despliegue real y puntual (`apply`, medir el coste y `destroy`) y
gold en Athena con `dbt-athena`. Según la
[estimación de costes](../architecture.md#5-trade-offs-costes-y-escalado), el lake cuesta céntimos y el gasto está en
el cómputo siempre encendido. Por eso el orden es primero el lake, después el cómputo por uso y, solo con usuarios,
un warehouse siempre encendido.
