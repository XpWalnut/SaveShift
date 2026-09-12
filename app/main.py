import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.database.database import init_db
from app.ui.main_window import MainWindow
from app.core.logging import logger
from app.core.resources import get_resource_path
from app.ui import styles

def main() -> None:
    logger.info("Save Shift started")
    init_db()

    startup_package_path: Path | None = None

    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])

        if candidate.suffix.lower() == ".sspkg":
            startup_package_path = candidate

    app = QApplication(sys.argv)
    app.setStyleSheet(styles.application_style())

    icon = QIcon(
        str(get_resource_path("assets/icons/SaveShift-Vaporwave.ico"))
    )
    app.setWindowIcon(icon)

    window = MainWindow(
        startup_package_path=startup_package_path,
    )
    window.setWindowIcon(icon)
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
