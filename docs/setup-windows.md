# Preparar Windows 10 LTSC 2021

Estado comprobado el 2026-10-24: Git 2.55 instalado; **Docker no instalado**; WSL presente pero sin
distribución; `make`, `gh` y Python no instalados (Python no hace falta).

## 1. WSL2 (PowerShell como administrador)

```powershell
wsl --install -d Ubuntu
```

Reinicia. Después limita la memoria de WSL creando `%UserProfile%\.wslconfig`:

```ini
[wsl2]
memory=8GB
processors=4
```

## 2. Docker Desktop

LTSC 2021 (build 19044) es compatible con Docker Desktop sobre WSL2. Descárgalo desde
docker.com, instala con la opción *Use WSL 2 based engine* y comprueba:

```powershell
docker version
docker compose version
```

## 3. Herramientas opcionales

```powershell
winget install ezwinports.make
winget install GitHub.cli
```

Sin `make` puedes usar los comandos equivalentes de `docker compose` que aparecen en el `Makefile`.

## 4. Primer arranque

```bash
make up            # ~10 min la primera vez (descarga imágenes y construye la de Airflow)
make run DAYS=1
```
