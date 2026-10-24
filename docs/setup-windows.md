# Preparar Windows 10 LTSC 2021 (WSL2 + Debian)

Estado comprobado el 2026-10-24: WSL2 con **Debian 13 (trixie)** instalado; dentro de Debian aún no
hay Docker, git, make ni curl. En Windows: Git 2.55, sin Python (no hace falta).

Se usa **Docker Engine dentro de Debian**, sin Docker Desktop: consume menos memoria, no necesita
licencia y es el mismo Docker que en un servidor Linux.

## 1. Memoria de WSL (PowerShell en Windows)

Crea `%UserProfile%\.wslconfig`:

```ini
[wsl2]
memory=10GB
processors=4
```

## 2. Activar systemd en Debian

Dentro de Debian:

```bash
printf '[boot]\nsystemd=true\n' | sudo tee /etc/wsl.conf
```

Desde PowerShell, reinicia WSL para aplicar ambos cambios:

```powershell
wsl --shutdown
```

## 3. Herramientas y Docker Engine (dentro de Debian)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git make
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Cierra y vuelve a abrir la terminal de Debian, y comprueba:

```bash
docker run --rm hello-world
docker compose version
```

## 4. Trabajar desde el sistema de ficheros de Linux

Los bind mounts desde `/mnt/c/...` son lentos y dan problemas de permisos. Clona el repo dentro
de Debian (VS Code lo abre con la extensión *WSL*: `code .`):

```bash
git config --global user.name "Alexandre Coll"
git config --global user.email "<tu email>"
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/<usuario>/MallorcaDataPlatform.git   # o, antes del primer push:
# git clone /mnt/c/Users/alexandre/Documents/MallorcaDataPlatform
cd MallorcaDataPlatform
```

## 5. Hooks de pre-commit

En cada `git commit`, ruff arregla (incluidos los arreglos *unsafe*) y formatea los ficheros
modificados antes de guardar el commit:

```bash
sudo apt install pre-commit
pre-commit install
```

## 6. Primer arranque

```bash
make up            # ~10 min la primera vez (descarga imágenes y construye la de Airflow)
make e2e           # ejecuta el DAG dos veces y comprueba idempotencia
```

Airflow, Grafana y MinIO se abren desde el navegador de Windows en `localhost` (WSL2 reenvía los puertos).

### Alternativa: Docker Desktop

Si prefieres interfaz gráfica, Docker Desktop también funciona con WSL2: activa
*Settings → Resources → WSL integration → Debian*. No instales los dos a la vez.
