from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .gui.main_window import MainWindow, apply_dark_palette


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_palette(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

