from PySide6.QtWidgets import QApplication
from pathlib import Path
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.database.database import init_db
from app.ui.main_window import MainWindow
from app.core.logging import logger

def get_resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_path / relative_path

def main() -> None:
    logger.info("Save Shift started")
    init_db()

    app = QApplication([])

    icon = QIcon(str(get_resource_path("assets/icons/SaveShift.ico")))
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    app.exec()


if __name__ == "__main__":
    main()