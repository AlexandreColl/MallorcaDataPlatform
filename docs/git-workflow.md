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

## Commits: gitmoji + Conventional Commits

`<emoji> tipo(ámbito): descripción` — el emoji en Unicode (✨, no `:sparkles:`) para que se vea igual en
GitHub, en la terminal y en el IDE. Ámbitos: `core`, `connector`, `airflow`, `dbt`, `grafana`, `infra`,
`deps`, `release`.

| Emoji | Tipo | Cuándo |
|---|---|---|
| ✨ | `feat` | nueva funcionalidad o conector |
| 🐛 | `fix` | corrección de un error |
| 📝 | `docs` | documentación |
| ♻️ | `refactor` | refactorización sin cambio de comportamiento |
| ✅ | `test` | añadir o arreglar tests |
| 👷 | `ci` | workflows de CI/CD |
| ⬆️ | `build(deps)` | actualizar dependencias |
| 🐳 | `build` | Docker, imágenes |
| ⚡️ | `perf` | rendimiento |
| 🔥 | `chore` | borrar código o ficheros |
| 🔧 | `chore` | configuración |
| 🔖 | `chore(release)` | publicar versión |
| 🎉 | `chore` | primer commit |
| 🔀 | — | merges (`🔀 Merge branch '...' into develop`) |

```
✨ feat(connector): add REData electricity demand for Balearic Islands
🐛 fix(core): keep non-null value when collapsing duplicates
```

El workflow `pr-title.yml` exige este formato en el título del PR (que es el mensaje del squash).

## Publicar una versión

```bash
git switch develop && git pull
git switch -c release/v0.2.0
# 1. sube la versión en pyproject.toml y core/__init__.py
# 2. mueve lo de [Unreleased] a [0.2.0] - AAAA-MM-DD en CHANGELOG.md
git commit -am "🔖 chore(release): v0.2.0"
git push -u origin release/v0.2.0      # PR a main; tras mergear:
git switch main && git pull
git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0
git switch develop && git merge --no-ff main && git push
```

El tag dispara `release.yml`: comprueba que coincide con `pyproject.toml`, crea la Release con las notas
del CHANGELOG y publica la imagen en `ghcr.io/<usuario>/mallorcadataplatform/airflow:<versión>`.

## Configuración inicial en GitHub (una vez)

Desde el clon de Debian:

```bash
sudo apt install gh
gh auth login                      # GitHub.com → HTTPS → login con el navegador
git remote rename origin windows   # el origin actual es la copia de Windows
gh repo create MallorcaDataPlatform --public --source . --remote origin \
  --description "Modular local data platform for Mallorca open data"
git push -u origin main develop
./scripts/github-setup.sh          # merge options + protección de ramas
```

### CI

No hay nada que activar: GitHub Actions ejecuta automáticamente los workflows de `.github/workflows/`
en cada push y PR. Cada job declara sus propios permisos (`permissions:`), así que no hace falta tocar
*Settings → Actions*. El primer push a `develop` lanza `CI`; los PR a `main`, además, `E2E`.

| Workflow | Jobs (nombre del check) | Cuándo |
|---|---|---|
| `ci.yml` | `Lint (ruff)`, `Unit tests (PySpark)`, `dbt build (empty warehouse)`, `Docker compose config + image build` | push a `main`/`develop`, todos los PR |
| `e2e.yml` | `e2e` | PR y push a `main`, lunes 05:00 UTC, manual |
| `pr-title.yml` | `conventional` | PR (título con gitmoji + Conventional Commits) |
| `release.yml` | `release` | tag `vX.Y.Z` |

### Protección de ramas

`scripts/github-setup.sh` la aplica con *rulesets* (configuración como código, se puede relanzar):

| Rama | Reglas |
|---|---|
| `develop` | PR obligatorio, los 4 checks de CI + título del PR, rama al día con la base, conversaciones resueltas, sin force-push ni borrado |
| `main` | lo mismo + `e2e` con las APIs reales |

No se exigen aprobaciones (0 reviewers) porque en un proyecto individual GitHub no deja aprobar tu
propio PR. Además fija `develop` como rama por defecto, squash merge para features, merge commit para
los PR de release y borrado automático de ramas mergeadas.

Se puede ver y editar en *Settings → Rules → Rulesets*.
