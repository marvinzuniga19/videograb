@echo off
REM VideoGrab - arranque en Windows
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
  echo Preparando el entorno por primera vez ^(esto tarda un par de minutos^)...
  %PY% -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo.
  echo Aviso: no se encontro ffmpeg.
  echo Sin ffmpeg no se pueden unir video+audio en alta calidad, convertir a MP3
  echo ni incrustar subtitulos. Instalalo abriendo PowerShell y ejecutando:
  echo    winget install Gyan.FFmpeg
  echo.
)

python server.py
pause
