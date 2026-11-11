from __future__ import annotations

from pathlib import Path
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from mcrdp.gui.main_window import MainWindow


def _startup_log_path() -> Path:
    return Path.home() / "Library" / "Logs" / "MCRDP_v6_startup.log"


def _write_startup_log(message: str) -> None:
    try:
        path = _startup_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def main() -> int:
    _write_startup_log("MCRDP_v6: starting")
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
        window.show()
        _write_startup_log("MCRDP_v6: window shown")
        return app.exec()
    except Exception as exc:
        _write_startup_log("MCRDP_v6: exception")
        _write_startup_log(traceback.format_exc())
        QMessageBox.critical(None, "MCRDP startup error", f"{type(exc).__name__}\n{exc}")
        raise
