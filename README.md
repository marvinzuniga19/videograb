# VideoGrab — uso en tu laptop

La app tiene dos partes: la interfaz (lo que ves) y el motor que descarga (Python + yt-dlp).
Para usarla en tu laptop hay que ejecutar el motor ahí, porque es el que baja los archivos
y los guarda en tu disco.

---

## 1. Requisitos

| Programa | Para qué sirve | Cómo instalarlo |
| --- | --- | --- |
| **Python 3.9 o superior** | ejecuta el motor | [python.org/downloads](https://www.python.org/downloads/) — en Windows marca la casilla **Add Python to PATH** |
| **ffmpeg** | unir video+audio en alta calidad, convertir a MP3, incrustar subtítulos | Windows: `winget install Gyan.FFmpeg` · macOS: `brew install ffmpeg` · Ubuntu: `sudo apt install ffmpeg` |

Sin ffmpeg la app arranca igual, pero se limita a la calidad ya combinada (normalmente 720p)
y no puede generar MP3 ni incrustar subtítulos.

---

## 2. Arrancar la app

1. Descomprime `videograb.zip` en una carpeta, por ejemplo `Documentos\videograb`.
2. Entra en la carpeta y haz doble clic en:
   - **Windows:** `iniciar.bat`
   - **macOS o Linux:** `iniciar.sh` (la primera vez, desde la Terminal: `chmod +x iniciar.sh && ./iniciar.sh`)
3. La primera vez tarda un par de minutos: crea un entorno aislado e instala las dependencias.
4. Se abrirá tu navegador en `http://localhost:8000` con la app lista.

Deja abierta la ventana negra (consola) mientras uses la app: ahí corre el motor.
Para cerrar todo, pulsa `Ctrl + C` en esa ventana o ciérrala.

### Si prefieres hacerlo a mano

```bash
cd videograb
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

---

## 2b. Versión de escritorio (ventana propia, sin navegador)

Si prefieres una app con su propia ventana, menús nativos y diálogo de guardado del
sistema, usa el modo escritorio. Es el mismo motor: solo cambia la envoltura.

- **Windows:** doble clic en `escritorio.bat`
- **macOS o Linux:** `chmod +x escritorio.sh && ./escritorio.sh`

La primera vez descarga PySide6 (unos 150 MB), así que tarda varios minutos. Después
abre directo, sin consola ni pestaña de navegador.

Diferencias con el modo navegador:

| | Navegador (`iniciar`) | Escritorio (`escritorio`) |
| --- | --- | --- |
| Instalación | ligera, unos 30 MB | unos 150 MB más por PySide6 |
| Ventana | una pestaña más | ventana propia con menús |
| Consola abierta | sí, hay que dejarla | no |
| Guardar archivos | diálogo del navegador | diálogo del sistema, con barra de progreso |
| Puerto | 8000 fijo | uno libre al azar, invisible |

A mano: `pip install -r requirements-escritorio.txt` y luego `python escritorio.py`.

### Convertirla en un ejecutable (.exe o .app)

Para que arranque con doble clic sin Python instalado, empaquétala con PyInstaller
**en el mismo sistema donde la vas a usar** (un .exe se genera en Windows, un .app en macOS):

```
.venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --windowed --name VideoGrab --add-data "static;static" escritorio.py
```

En macOS y Linux activa el entorno con `source .venv/bin/activate` y cambia el separador
de `--add-data` por dos puntos: `--add-data "static:static"`. El resultado queda en
`dist/VideoGrab/`.

Dos avisos útiles: el paquete pesa bastante (300 MB o más, porque incluye el motor de
navegador de Qt), y **ffmpeg sigue siendo externo**, así que o lo instalas en el sistema
o copias `ffmpeg.exe` junto al ejecutable.

---

## 2c. Recuerda el tamaño y la posición

La ventana vuelve a abrirse donde y como la dejaste: mismo tamaño, misma posición, y
maximizada si así la cerraste. También conserva por separado el tamaño normal, para que al
desmaximizar recuperes el de siempre en lugar de uno cualquiera.

Dos casos que están resueltos:

- **Cambiaste de monitor.** Si la posición guardada ya no cae en ninguna pantalla (por
  ejemplo, dejaste la app en un monitor externo y ahora no está conectado), la ventana se
  centra en la pantalla principal en lugar de abrirse donde no puedas verla.
- **Pantalla pequeña.** El tamaño inicial nunca excede el espacio disponible, así que no
  aparece más grande que tu pantalla.

Si quieres volver al punto de partida, usa **Ver → Restablecer el tamaño de la ventana**:
la centra con su tamaño original y olvida lo guardado.

---

## 2d. Icono en la bandeja del sistema

La versión de escritorio deja un icono junto al reloj. Un clic muestra u oculta la ventana,
y con el botón derecho aparece un menú con: mostrar u ocultar la ventana, abrir la carpeta
de descargas, "Acerca de" y Salir.

Por omisión, **cerrar la ventana no cierra la app**: se queda en la bandeja y te avisa la
primera vez para que no la pierdas de vista. Así sigue a mano sin ocupar la barra de tareas.
Para cerrarla de verdad usa **Salir**, en el menú de la bandeja o en Archivo (Ctrl+Q).

Si prefieres que la X cierre todo, desmarca **Ver → Al cerrar, seguir en la bandeja**. La
preferencia se guarda y se respeta la próxima vez.

Cuando una descarga termina con la ventana oculta, el sistema te lo notifica con el nombre
del archivo y la carpeta donde quedó. Con la ventana a la vista no notifica nada: el aviso
ya lo ves en la barra de estado.

En escritorios de Linux sin bandeja (algunas versiones de GNOME sin extensiones), la app
funciona igual y la opción aparece desactivada: la ventana se cierra de forma normal.

---

## 2e. Arrastrar y soltar enlaces

No hace falta copiar y pegar. Arrastra el enlace hasta la ventana y suéltalo: aparece un
aviso y el análisis arranca solo. Funciona igual en el navegador y en la versión de
escritorio, y acepta tres formas de soltar:

- un enlace arrastrado desde otra pestaña o desde los favoritos,
- texto seleccionado que tenga una dirección dentro, aunque venga con más palabras,
- un trozo de página copiado, del que se toma el primer enlace.

Si lo que sueltas no trae ninguna dirección, te lo dice y no hace nada. En la versión de
escritorio la ventana nunca se va a otro sitio al soltar: los enlaces ajenos a la app se
abren en tu navegador de siempre.

---

## 3. Dónde quedan los archivos

Cada descarga se guarda en la subcarpeta `downloads/` dentro de la carpeta de la app,
en un directorio propio por descarga. El botón **Guardar** del navegador también te deja
copiarlos a donde quieras (Descargas, escritorio, etc.).

Puedes borrar `downloads/` cuando quieras para liberar espacio.

---

## 4. Mantenimiento

Los sitios web cambian a menudo y yt-dlp se actualiza para seguirles el paso. Si algún
sitio deja de funcionar, actualiza el motor:

```bash
cd videograb
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -U yt-dlp
```

---

## 5. Problemas frecuentes

| Síntoma | Causa y solución |
| --- | --- |
| "python no se reconoce como un comando" | Python no está en el PATH. Reinstálalo marcando **Add Python to PATH**. |
| La página no carga en `localhost:8000` | El puerto está ocupado. Arranca con otro: `PORT=8100 python server.py` (Windows: `set PORT=8100` y luego `python server.py`). |
| Falla al elegir 1080p o más | Falta ffmpeg. Instálalo y reinicia la app. |
| "Este video requiere iniciar sesión" | Es contenido privado o restringido; la app solo trabaja con material público, propio o con permiso. |
| Un sitio que antes funcionaba ya no | Actualiza yt-dlp (sección 4). |

---

## 6. Detalle técnico

- `server.py` — motor Flask sobre yt-dlp. Sirve también la interfaz, así que todo va por un
  solo puerto (8000 por omisión, configurable con la variable `PORT`).
- `escritorio.py` — envoltura PySide6: levanta el mismo servidor en un hilo, en un puerto
  libre, y lo muestra en un `QWebEngineView`. Las descargas pasan por el diálogo nativo
  del sistema.
- `static/` — interfaz: `index.html`, `styles.css`, `app.js`, `icono.svg`.
- Solo escucha en `127.0.0.1`, es decir, nadie de tu red puede entrar a la app.
- Ninguna dirección ni descarga sale de tu equipo hacia servidores propios: el motor habla
  directamente con el sitio de origen.

**Uso responsable:** descarga únicamente contenido público, propio o con permiso de su autor.
La app no elude protecciones DRM ni accede a contenido privado o de pago.
