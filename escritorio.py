#!/usr/bin/env python3
"""VideoGrab — version de escritorio (PySide6).

Arranca el mismo servidor Flask dentro del propio programa, en un puerto libre y
escuchando solo en 127.0.0.1, y muestra la interfaz en una ventana nativa.
No hace falta abrir el navegador ni dejar una consola abierta.

    python escritorio.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--autoplay-policy=no-user-gesture-required")

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSystemTrayIcon,
)
from werkzeug.serving import make_server

import server as backend

BASE_DIR = Path(__file__).parent.resolve()
APP_NAME = "VideoGrab"

# la ventana nativa toma los mismos colores que la interfaz web
ESTILO = """
QMainWindow, QWidget { background: #080a0e; }
QMenuBar {
  background: #0b0e13;
  color: #d7dee8;
  border-bottom: 1px solid #1d2531;
  padding: 2px 4px;
}
QMenuBar::item { padding: 5px 11px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected { background: #172033; color: #58e1b0; }
QMenu {
  background: #0d1118;
  color: #d7dee8;
  border: 1px solid #1d2531;
  padding: 5px;
}
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 6px; }
QMenu::item:selected { background: #172033; color: #58e1b0; }
QMenu::separator { height: 1px; background: #1d2531; margin: 5px 8px; }
QStatusBar {
  background: #0b0e13;
  color: #8d9aab;
  border-top: 1px solid #1d2531;
}
QStatusBar::item { border: none; }
QProgressBar {
  background: #172033;
  border: none;
  border-radius: 4px;
  height: 8px;
}
QProgressBar::chunk { background: #58e1b0; border-radius: 4px; }
QMessageBox { background: #0d1118; color: #d7dee8; }
QMessageBox QLabel { color: #d7dee8; }
QPushButton {
  background: #172033;
  color: #d7dee8;
  border: 1px solid #263145;
  border-radius: 8px;
  padding: 6px 16px;
}
QPushButton:hover { border-color: #58e1b0; color: #58e1b0; }
"""


# --------------------------------------------------------------------------- #
# servidor local en un hilo
# --------------------------------------------------------------------------- #
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalServer(threading.Thread):
    """Sirve la app Flask en 127.0.0.1 y permite cerrarla de forma ordenada."""

    def __init__(self, port: int):
        super().__init__(daemon=True)
        self.srv = make_server("127.0.0.1", port, backend.app, threaded=True)
        self.port = port

    def run(self) -> None:
        self.srv.serve_forever()

    def stop(self) -> None:
        self.srv.shutdown()


# --------------------------------------------------------------------------- #
# pagina: la ventana nunca se va de la app
# --------------------------------------------------------------------------- #
class Pagina(QWebEnginePage):
    """Al soltar un enlace, el navegador embebido intentaria abrirlo.

    Aqui se bloquea cualquier salida de la app: del enlace se encarga la interfaz
    y, si el usuario abre algo pensado para el exterior, se manda al navegador
    del sistema.
    """

    def __init__(self, parent=None, puerto: int = 0):
        super().__init__(parent)
        self.puerto = puerto

    def _es_local(self, url: QUrl) -> bool:
        return url.host() in ("127.0.0.1", "localhost") and url.port() == self.puerto

    def acceptNavigationRequest(self, url: QUrl, tipo, es_principal: bool) -> bool:  # noqa: N802
        if url.scheme() in ("about", "blob", "data") or self._es_local(url):
            return True
        QDesktopServices.openUrl(url)
        return False

    def createWindow(self, _tipo):  # noqa: N802
        return None


# --------------------------------------------------------------------------- #
# ventana
# --------------------------------------------------------------------------- #
class Ventana(QMainWindow):
    TAM_POR_OMISION = (1180, 860)

    def __init__(self, port: int):
        super().__init__()
        self.ajustes = QSettings(APP_NAME, APP_NAME)
        self.setWindowTitle(APP_NAME)
        self.resize(*self.TAM_POR_OMISION)
        self.setMinimumSize(420, 500)

        icono = BASE_DIR / "static" / "icono.svg"
        if icono.exists():
            self.setWindowIcon(QIcon(str(icono)))

        self.vista = QWebEngineView(self)
        self.pagina = Pagina(self.vista, port)
        self.vista.setPage(self.pagina)
        self.setCentralWidget(self.vista)
        self.vista.load(QUrl(f"http://127.0.0.1:{port}/"))

        self.barra = QProgressBar()
        self.barra.setMaximumWidth(220)
        self.barra.setTextVisible(False)
        self.barra.hide()
        self.statusBar().addPermanentWidget(self.barra)
        self.statusBar().showMessage("Listo")

        self.vista.page().profile().downloadRequested.connect(self.al_descargar)

        self.saliendo = False
        self.aviso_dado = False
        self.bandeja: QSystemTrayIcon | None = None
        self._menus()
        self._bandeja()
        self._restaurar_geometria()

    # ------------------------------ menus ------------------------------ #
    def _menus(self) -> None:
        archivo = self.menuBar().addMenu("&Archivo")

        abrir = QAction("Abrir carpeta de descargas", self)
        abrir.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(backend.DOWNLOAD_DIR)))
        )
        archivo.addAction(abrir)

        archivo.addSeparator()
        salir = QAction("Salir", self)
        salir.setShortcut("Ctrl+Q")
        salir.triggered.connect(self.salir)
        archivo.addAction(salir)

        ver = self.menuBar().addMenu("&Ver")
        recargar = QAction("Recargar", self)
        recargar.setShortcut("Ctrl+R")
        recargar.triggered.connect(self.vista.reload)
        ver.addAction(recargar)

        restablecer = QAction("Restablecer el tamaño de la ventana", self)
        restablecer.triggered.connect(self.restablecer_geometria)
        ver.addAction(restablecer)

        ver.addSeparator()
        self.acc_minimizar = QAction("Al cerrar, seguir en la bandeja", self)
        self.acc_minimizar.setCheckable(True)
        ver.addAction(self.acc_minimizar)

        ayuda = self.menuBar().addMenu("A&yuda")
        acerca = QAction("Acerca de VideoGrab", self)
        acerca.triggered.connect(self.al_acerca)
        ayuda.addAction(acerca)

    # --------------------------- geometria ----------------------------- #
    def _restaurar_geometria(self) -> None:
        """Devuelve la ventana al tamaño y sitio donde la dejaste la vez anterior."""
        guardada = self.ajustes.value("ventana/geometria")
        if guardada and self.restoreGeometry(guardada):
            self._asegurar_en_pantalla()
        else:
            self._centrar()

        if self.ajustes.value("ventana/maximizada", False, type=bool):
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def _guardar_geometria(self) -> None:
        """Se llama al cerrar o al esconder la ventana en la bandeja."""
        maximizada = bool(self.windowState() & Qt.WindowMaximized)
        self.ajustes.setValue("ventana/maximizada", maximizada)
        if not maximizada and not self.isMinimized():
            # con la ventana maximizada se conserva la geometria anterior,
            # para que al desmaximizar vuelva a su tamano normal
            self.ajustes.setValue("ventana/geometria", self.saveGeometry())

    def _asegurar_en_pantalla(self) -> None:
        """Si desconectaste el monitor donde estaba, la traemos de vuelta."""
        marco = self.frameGeometry()
        for pantalla in QApplication.screens():
            if pantalla.availableGeometry().intersects(marco):
                return
        self._centrar()

    def _centrar(self) -> None:
        pantalla = self.screen() or QApplication.primaryScreen()
        if not pantalla:
            return
        libre = pantalla.availableGeometry()
        ancho = min(self.TAM_POR_OMISION[0], libre.width() - 80)
        alto = min(self.TAM_POR_OMISION[1], libre.height() - 80)
        self.resize(max(ancho, self.minimumWidth()), max(alto, self.minimumHeight()))
        marco = self.frameGeometry()
        marco.moveCenter(libre.center())
        self.move(marco.topLeft())

    @Slot()
    def restablecer_geometria(self) -> None:
        self.ajustes.remove("ventana/geometria")
        self.ajustes.remove("ventana/maximizada")
        self.setWindowState(self.windowState() & ~Qt.WindowMaximized)
        self._centrar()
        self.statusBar().showMessage("Tamaño de ventana restablecido", 4000)

    # ----------------------------- bandeja ----------------------------- #
    def _bandeja(self) -> None:
        """Icono junto al reloj: deja la app a mano sin ocupar la barra de tareas."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # algunos escritorios de Linux no tienen bandeja; se cierra normal
            self.acc_minimizar.setEnabled(False)
            self.acc_minimizar.setText("Al cerrar, seguir en la bandeja (no disponible)")
            return

        guardado = self.ajustes.value("bandeja/minimizar", True, type=bool)
        self.acc_minimizar.setChecked(guardado)
        self.acc_minimizar.toggled.connect(
            lambda on: self.ajustes.setValue("bandeja/minimizar", on)
        )

        self.bandeja = QSystemTrayIcon(self.windowIcon(), self)
        self.bandeja.setToolTip(f"{APP_NAME} — descargador de video")

        menu = QMenu(self)
        self.acc_mostrar = QAction("Ocultar ventana", self)
        self.acc_mostrar.triggered.connect(self.alternar_ventana)
        menu.addAction(self.acc_mostrar)

        descargas = QAction("Abrir carpeta de descargas", self)
        descargas.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(backend.DOWNLOAD_DIR)))
        )
        menu.addAction(descargas)

        menu.addSeparator()
        acerca = QAction("Acerca de VideoGrab", self)
        acerca.triggered.connect(self.al_acerca)
        menu.addAction(acerca)

        menu.addSeparator()
        salir = QAction("Salir", self)
        salir.triggered.connect(self.salir)
        menu.addAction(salir)

        self.bandeja.setContextMenu(menu)
        self.bandeja.activated.connect(self.al_pulsar_bandeja)
        self.bandeja.show()

    @Slot(QSystemTrayIcon.ActivationReason)
    def al_pulsar_bandeja(self, motivo: QSystemTrayIcon.ActivationReason) -> None:
        razones = QSystemTrayIcon.ActivationReason
        if motivo in (razones.Trigger, razones.DoubleClick):
            self.alternar_ventana()

    @Slot()
    def alternar_ventana(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self._guardar_geometria()
            self._maximizada_al_ocultar = bool(self.windowState() & Qt.WindowMaximized)
            self.hide()
        else:
            # al volver de la bandeja se respeta si estaba maximizada
            if getattr(self, "_maximizada_al_ocultar", False):
                self.showMaximized()
            else:
                self.showNormal()
            self.raise_()
            self.activateWindow()
        self._texto_bandeja()

    def _texto_bandeja(self) -> None:
        if hasattr(self, "acc_mostrar"):
            visible = self.isVisible() and not self.isMinimized()
            self.acc_mostrar.setText("Ocultar ventana" if visible else "Mostrar ventana")

    def avisar(self, titulo: str, texto: str) -> None:
        """Notificacion del sistema, solo cuando la ventana no esta a la vista."""
        if self.bandeja and not (self.isVisible() and not self.isMinimized()):
            self.bandeja.showMessage(titulo, texto, self.windowIcon(), 5000)

    # ------------------------------ cierre ----------------------------- #
    @Slot()
    def salir(self) -> None:
        """Cierre de verdad, tambien si la ventana estaba oculta en la bandeja."""
        self.saliendo = True
        self.close()
        if self.bandeja:
            self.bandeja.hide()
        QApplication.quit()

    def closeEvent(self, evento) -> None:  # noqa: N802
        self._guardar_geometria()
        a_bandeja = self.bandeja is not None and self.acc_minimizar.isChecked()
        if self.saliendo or not a_bandeja:
            if self.bandeja:
                self.bandeja.hide()
            evento.accept()
            return

        evento.ignore()
        self.hide()
        self._texto_bandeja()
        if not self.aviso_dado:
            self.aviso_dado = True
            self.bandeja.showMessage(
                APP_NAME,
                "Sigue funcionando aquí. Pulsa el icono para volver, o usa Salir para cerrarla.",
                self.windowIcon(),
                6000,
            )

    @Slot()
    def al_acerca(self) -> None:
        import yt_dlp

        QMessageBox.information(
            self,
            f"Acerca de {APP_NAME}",
            f"<b>{APP_NAME}</b><br>Descargador de video para uso personal."
            f"<br><br>Motor: yt-dlp {yt_dlp.version.__version__}"
            f"<br>Interfaz: PySide6 sobre Flask"
            f"<br><br>Descarga únicamente contenido público, propio o con permiso "
            f"de su autor. La app no elude protecciones DRM.",
        )

    # ---------------------------- descargas ---------------------------- #
    @Slot(QWebEngineDownloadRequest)
    def al_descargar(self, item: QWebEngineDownloadRequest) -> None:
        sugerido = item.suggestedFileName() or "video"
        carpeta = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or str(Path.home())
        destino = self.pedir_destino(str(Path(carpeta) / sugerido))
        if not destino:
            item.cancel()
            self.statusBar().showMessage("Guardado cancelado", 4000)
            return

        ruta = Path(destino)
        item.setDownloadDirectory(str(ruta.parent))
        item.setDownloadFileName(ruta.name)
        item.receivedBytesChanged.connect(lambda: self._progreso(item))
        item.stateChanged.connect(lambda estado: self._estado(estado, ruta))
        item.accept()
        self.barra.setRange(0, 0)
        self.barra.show()
        self.statusBar().showMessage(f"Guardando {ruta.name}…")

    def pedir_destino(self, sugerido: str) -> str:
        """Dialogo nativo de guardado (se sustituye en las pruebas automaticas)."""
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar como", sugerido)
        return destino

    def _progreso(self, item: QWebEngineDownloadRequest) -> None:
        total = item.totalBytes()
        if total > 0:
            self.barra.setRange(0, 100)
            self.barra.setValue(int(item.receivedBytes() * 100 / total))

    def _estado(self, estado: QWebEngineDownloadRequest.DownloadState, ruta: Path) -> None:
        estados = QWebEngineDownloadRequest.DownloadState
        if estado == estados.DownloadCompleted:
            self.barra.hide()
            self.statusBar().showMessage(f"Guardado en {ruta}", 8000)
            self.avisar("Descarga lista", f"{ruta.name} se guardó en {ruta.parent}")
        elif estado == estados.DownloadInterrupted:
            self.barra.hide()
            self.statusBar().showMessage("El guardado se interrumpió", 8000)
            self.avisar("Descarga interrumpida", f"No se pudo guardar {ruta.name}")
        elif estado == estados.DownloadCancelled:
            self.barra.hide()
            self.statusBar().showMessage("Guardado cancelado", 4000)


# --------------------------------------------------------------------------- #
def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setStyleSheet(ESTILO)

    puerto = free_port()
    srv = LocalServer(puerto)
    srv.start()

    ventana = Ventana(puerto)
    ventana.show()

    # con bandeja, ocultar la ventana no debe cerrar el programa
    app.setQuitOnLastWindowClosed(ventana.bandeja is None)

    app.aboutToQuit.connect(srv.stop)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
