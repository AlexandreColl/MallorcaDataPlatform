# Flujo de trabajo con Git

## Ramas

| Rama | Uso | Protección |
|---|---|---|
| `main` | Solo versiones publicadas. Cada merge lleva un tag `vX.Y.Z` | PR obligatorio, CI + E2E en verde, sin push directo |
| `develop` | Integración. Aquí se mergean las features | PR obligatorio, CI en verde |
| `feature/<tema>` | Una funcionalidad o conector (`feature/connector-redata`) | — |
| `fix/<tema>` | Corrección | — |
| `release/vX.Y.Z` | Preparar versión: bump de versión y CHANGELOG | — |
| `hotfix/vX.Y.Z` | Corrección urgente desde `main` | — |

```
feature/connector-redata ──PR(squash)──► develop ──PR(release/v0.2.0)──► main ──tag v0.2.0──► Release
```

## Commits: Conventional Commits

`tipo(ámbito): descripción` — tipos `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `build`, `chore`, `perf`;
ámbitos `core`, `connector`, `airflow`, `dbt`, `grafana`, `infra`, `deps`, `release`.

```
feat(connector): add REData electricity demand for Balearic Islands
fix(core): keep non-null value when collapsing duplicates
```

El workflow `pr-title.yml` exige este formato en el título del PR (que es el mensaje del squash).

## Publicar una versión

```bash
git switch develop && git pull
git switch -c release/v0.2.0
# 1. sube la versión en pyproject.toml y core/__init__.py
# 2. mueve lo de [Unreleased] a [0.2.0] - AAAA-MM-DD en CHANGELOG.md
git commit -am "chore(release): v0.2.0"
git push -u origin release/v0.2.0      # PR a main; tras mergear:
git switch main && git pull
git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0
git switch develop && git merge --no-ff main && git push
```

El tag dispara `release.yml`: comprueba que coincide con `pyproject.toml`, crea la Release con las notas
del CHANGELOG y publica la imagen en `ghcr.io/<usuario>/mallorcadataplatform/airflow:<versión>`.

## Configuración inicial en GitHub (una vez)

```bash
gh repo create MallorcaDataPlatform --public --source . --remote origin
git push -u origin main develop
gh repo edit --default-branch develop --enable-squash-merge --enable-merge-commit=false --delete-branch-on-merge
```

Protección de ramas (Settings → Rules → Rulesets, o con la API):

- `main`: requerir PR, checks `Lint (ruff)`, `Unit tests (PySpark)`, `dbt build (empty warehouse)`,
  `Docker compose config + image build`, `e2e`; bloquear force-push y borrado.
- `develop`: requerir PR y los cuatro checks de CI.
