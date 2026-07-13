from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from app.ui import styles, theme
from app.updates.models import UpdateRelease
from app.version import APP_VERSION


class UpdateAvailableDialog(QDialog):
    def __init__(
        self,
        release: UpdateRelease,
        automatic_update_checks: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.release = release

        self.setWindowTitle("Save Shift Update Available")
        self.setMinimumSize(600, 440)

        heading = QLabel(f"Save Shift {release.version} is available")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        version_label = QLabel(
            f"Installed: {APP_VERSION}    Available: {release.version}"
        )
        version_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        release_notes_label = QLabel("Release notes")
        release_notes_label.setStyleSheet("font-weight: bold;")

        self.release_notes = QTextBrowser()
        self.release_notes.setPlainText(release.notes)
        self.release_notes.setOpenExternalLinks(True)

        self.automatic_update_checkbox = QCheckBox(
            "Automatically check for Save Shift updates"
        )
        self.automatic_update_checkbox.setChecked(automatic_update_checks)

        not_now_button = QPushButton("Not Now")
        not_now_button.setStyleSheet(styles.secondary_button_style())
        not_now_button.clicked.connect(self.reject)

        update_button = QPushButton("Update Now")
        update_button.setStyleSheet(styles.primary_button_style())
        update_button.clicked.connect(self.accept)
        update_button.setDefault(True)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(not_now_button)
        button_row.addWidget(update_button)

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
        layout.addWidget(release_notes_label)
        layout.addWidget(self.release_notes, 1)
        layout.addWidget(self.automatic_update_checkbox)
        layout.addLayout(button_row)
        self.setLayout(layout)
        self.setStyleSheet(
            f"background-color: {theme.WINDOW_BACKGROUND}; color: {theme.TEXT_PRIMARY};"
        )

    @property
    def automatic_update_checks(self) -> bool:
        return self.automatic_update_checkbox.isChecked()
