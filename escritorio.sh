#!/usr/bin/env bash
# VideoGrab — version de escritorio en macOS y Linux
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3. Instalalo desde https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Preparando el entorno por primera vez (descarga unos 150 MB, tarda varios minutos)..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-escritorio.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo
  echo "Aviso: no se encontro ffmpeg. Sin el no hay alta calidad, MP3 ni subtitulos incrustados."
  echo "  macOS:  brew install ffmpeg"
  echo "  Ubuntu: sudo apt install ffmpeg"
  echo
fi

python escritorio.py
