from PySide6.QtWidgets import QApplication

from app.database.database import init_db
from app.ui.main_window import MainWindow
from app.utils.logging import logger


def main() -> None:
    init_db()

    app = QApplication([])
    window = MainWindow()
    window.show()

    app.exec()

    logger.info("Save Shift started")


if __name__ == "__main__":
    main()