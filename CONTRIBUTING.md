# Contribuir

- Flujo de ramas, commits y releases: [docs/git-workflow.md](docs/git-workflow.md)
- Añadir una fuente de datos: [docs/adding-a-connector.md](docs/adding-a-connector.md)

Antes de abrir un PR:

```bash
make lint
make test
make e2e        # con la plataforma levantada
```

Reglas del proyecto:

1. El dato crudo (bronze) nunca se modifica ni se borra.
2. Marcar un dato como sospechoso y corregirlo son pasos distintos.
3. Relanzar cualquier ventana no duplica filas.
4. Las claves van en `.env`, nunca en el repositorio.
