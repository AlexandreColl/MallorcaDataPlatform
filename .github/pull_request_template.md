## Qué cambia

<!-- Resumen en 1-3 frases. Título: gitmoji + Conventional Commits, p. ej. "✨ feat(connector): add REData" -->
<!-- Tabla de emojis en docs/git-workflow.md -->

## Tipo

- [ ] Nuevo conector
- [ ] Núcleo (core / quality / pipeline)
- [ ] Infra (Docker, Airflow, CI)
- [ ] dbt / Grafana
- [ ] Docs

## Checklist

- [ ] Tests unitarios añadidos o actualizados (`make test`)
- [ ] `make lint` sin errores
- [ ] Si es un conector: `connector.yaml`, fixtures grabadas en `tests/fixtures`, sección en el README
- [ ] Sin secretos en el código (van en `.env`)
- [ ] `CHANGELOG.md` actualizado en la sección *Unreleased*
