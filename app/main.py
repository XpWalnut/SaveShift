from PySide6.QtWidgets import QApplication

from app.database.database import init_db
from app.ui.main_window import MainWindow
from app.core.logging import logger


def main() -> None:
    logger.info("Save Shift started")
    init_db()

    app = QApplication([])
    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()