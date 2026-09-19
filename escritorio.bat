@echo off
REM VideoGrab - version de escritorio en Windows
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Falta Python 3. Instalalo desde https://www.python.org/downloads/
  echo Marca la casilla "Add Python to PATH" durante la instalacion.
  pause
  exit /b 1
)

if not exist .venv (
  echo Preparando el entorno por primera vez ^(descarga unos 150 MB, tarda varios minutos^)...
  %PY% -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-escritorio.txt

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo.
  echo Aviso: no se encontro ffmpeg. Sin el no hay alta calidad, MP3 ni subtitulos incrustados.
  echo Instalalo con:  winget install Gyan.FFmpeg
  echo.
)

start "" pythonw escritorio.py
