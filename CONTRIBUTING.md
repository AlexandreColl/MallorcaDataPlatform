# Contribuir

- Flujo de ramas, commits y releases: [docs/git-workflow.md](docs/git-workflow.md)
- Añadir una fuente de datos: [docs/adding-a-connector.md](docs/adding-a-connector.md)

Una vez por clon, instala los hooks para que ruff arregle y formatee en cada commit:

```bash
pre-commit install
```

Antes de abrir un PR:

```bash
make lint       # solo informa, igual que la CI
make test
make e2e        # con la plataforma levantada
```

## Estilo de código

Ruff con **todas** las reglas activadas (`select = ["ALL"]`), líneas de 120 caracteres, arreglos
*unsafe* habilitados y Python 3.14. Las pocas excepciones están justificadas una a una en
`pyproject.toml`. `make format` (o el hook de pre-commit) aplica los arreglos y el formato; lo que
ruff no puede arreglar solo (docstrings, tipos, diseño de funciones) hay que corregirlo a mano.

Reglas del proyecto:

1. El dato crudo (bronze) nunca se modifica ni se borra.
2. Marcar un dato como sospechoso y corregirlo son pasos distintos.
3. Relanzar cualquier ventana no duplica filas.
4. Las claves van en `.env`, nunca en el repositorio.
