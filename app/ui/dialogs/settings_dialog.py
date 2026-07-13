from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.core.settings import AppSettings
from app.ui import styles, theme
from app.version import APP_VERSION


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.check_requested = False

        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)

        heading = QLabel("Update Settings")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        version_label = QLabel(f"Installed version: {APP_VERSION}")
        version_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        self.automatic_update_checkbox = QCheckBox(
            "Automatically check for Save Shift updates"
        )
        self.automatic_update_checkbox.setChecked(
            settings.automatic_update_checks
        )

        self.check_now_button = QPushButton("Check for Updates")
        self.check_now_button.setStyleSheet(styles.secondary_button_style())
        self.check_now_button.clicked.connect(self._request_check)

        close_button = QPushButton("Save and Close")
        close_button.setStyleSheet(styles.primary_button_style())
        close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        button_row.addWidget(self.check_now_button)
        button_row.addStretch()
        button_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
        )
        layout.setSpacing(theme.SPACING)
        layout.addWidget(heading)
        layout.addWidget(version_label)
        layout.addSpacing(theme.SPACING_SMALL)
        layout.addWidget(self.automatic_update_checkbox)
        layout.addSpacing(theme.SPACING)
        layout.addLayout(button_row)
        self.setLayout(layout)
        self.setStyleSheet(
            f"background-color: {theme.WINDOW_BACKGROUND}; color: {theme.TEXT_PRIMARY};"
        )

    @property
    def automatic_update_checks(self) -> bool:
        return self.automatic_update_checkbox.isChecked()

    def _request_check(self) -> None:
        self.check_requested = True
        self.accept()
