"""Arranque de la aplicacion."""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from .mainwindow import MainWindow


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(argv)
    app.setApplicationName("CircuitDraw")
    app.setStyle("Fusion")

    window = MainWindow()
    if len(argv) > 1:
        try:
            window.load_path(argv[1])
        except Exception as error:  # noqa: BLE001
            print(f"No se pudo abrir {argv[1]}: {error}", file=sys.stderr)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
