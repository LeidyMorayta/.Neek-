#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "Este instalador está diseñado para Oracle Ampere A1 (ARM64/aarch64)."
  echo "Arquitectura detectada: $(uname -m). No se realizaron cambios."
  exit 1
fi
if [[ "${USER:-}" != "ubuntu" ]]; then
  echo "Ejecuta este script conectado como usuario ubuntu (sin sudo delante)."
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo '[1/4] Instalando paquetes del sistema...'
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates bzip2 nginx unzip certbot python3-certbot-nginx

echo '[2/4] Preparando Miniforge para Linux ARM64...'
if [[ ! -x "$HOME/miniforge3/bin/conda" ]]; then
  curl -fL --retry 3 'https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh' -o /tmp/Miniforge3-Linux-aarch64.sh
  bash /tmp/Miniforge3-Linux-aarch64.sh -b -p "$HOME/miniforge3"
fi

echo '[3/4] Creando/actualizando entorno fieldshift desde environment.yml...'
if [[ -x "$HOME/miniforge3/envs/fieldshift/bin/python" ]]; then
  "$HOME/miniforge3/bin/conda" env update -n fieldshift -f environment.yml --prune
else
  "$HOME/miniforge3/bin/conda" env create -f environment.yml
fi

echo '[4/4] Ejecutando pruebas del motor y API...'
"$HOME/miniforge3/bin/conda" run -n fieldshift python -m pytest -q

echo ''
echo 'Dependencias instaladas. Siguiente: incorporar datos reales, comprobar /ready y activar systemd + Nginx.'
