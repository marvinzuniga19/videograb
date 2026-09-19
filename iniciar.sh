#!/usr/bin/env bash
# VideoGrab — arranque en macOS y Linux
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3. Instalalo desde https://www.python.org/downloads/ y vuelve a ejecutar este archivo."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Preparando el entorno por primera vez (esto tarda un par de minutos)..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo
  echo "Aviso: no se encontro ffmpeg."
  echo "Sin ffmpeg no se pueden unir video+audio en alta calidad, convertir a MP3"
  echo "ni incrustar subtitulos. Instalalo con:"
  echo "  macOS:  brew install ffmpeg"
  echo "  Ubuntu: sudo apt install ffmpeg"
  echo
fi

python server.py
