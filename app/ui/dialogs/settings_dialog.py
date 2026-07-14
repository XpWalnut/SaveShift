import platform

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.setMinimumWidth(540)

        update_heading = QLabel("Update Settings")
        update_heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        version_label = QLabel(f"Installed version: {APP_VERSION}")
        version_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        profile_heading = QLabel("Profile")
        profile_heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        profile_description = QLabel(
            "This name is recorded in project history and shown to friends "
            "when you hold a project lock."
        )
        profile_description.setWordWrap(True)
        profile_description.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        self.player_display_name_input = QLineEdit(
            settings.player_display_name
        )
        self.player_display_name_input.setPlaceholderText("Your name")

        profile_form = QFormLayout()
        profile_form.addRow("Display name", self.player_display_name_input)

        self.automatic_update_checkbox = QCheckBox(
            "Automatically check for Save Shift updates"
        )
        self.automatic_update_checkbox.setChecked(
            settings.automatic_update_checks
        )

        coordination_heading = QLabel("Project Coordination")
        coordination_heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        coordination_description = QLabel(
            "Coordinate project leases through any Save Shift-compatible HTTPS provider."
        )
        coordination_description.setWordWrap(True)
        coordination_description.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY};"
        )

        self.coordination_enabled_checkbox = QCheckBox(
            "Enable coordinated project locking"
        )
        self.coordination_enabled_checkbox.setChecked(
            settings.coordination_enabled
        )
        self._paired_device_id = settings.coordination_device_id

        self.coordination_server_input = QLineEdit(
            settings.coordination_server_url
        )
        self.coordination_server_input.setPlaceholderText(
            "https://saveshift-coordination.example.workers.dev"
        )

        self.coordination_device_name_input = QLineEdit(
            settings.coordination_device_name or platform.node() or "Windows PC"
        )

        self.coordination_pairing_code_input = QLineEdit()
        self.coordination_pairing_code_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.coordination_pairing_code_input.setPlaceholderText(
            "Required when pairing or changing providers"
        )

        self.coordination_status_label = QLabel()
        self.coordination_status_label.setWordWrap(True)
        self.coordination_status_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY};"
        )
        self.coordination_enabled_checkbox.toggled.connect(
            self._coordination_enabled_changed
        )
        self._coordination_enabled_changed(settings.coordination_enabled)

        coordination_form = QFormLayout()
        coordination_form.addRow("Provider URL", self.coordination_server_input)
        coordination_form.addRow("Computer name", self.coordination_device_name_input)
        coordination_form.addRow("Pairing code", self.coordination_pairing_code_input)

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
        layout.addWidget(profile_heading)
        layout.addWidget(profile_description)
        layout.addLayout(profile_form)
        layout.addSpacing(theme.SPACING)
        layout.addWidget(update_heading)
        layout.addWidget(version_label)
        layout.addWidget(self.automatic_update_checkbox)
        layout.addSpacing(theme.SPACING)
        layout.addWidget(coordination_heading)
        layout.addWidget(coordination_description)
        layout.addWidget(self.coordination_enabled_checkbox)
        layout.addLayout(coordination_form)
        layout.addWidget(self.coordination_status_label)
        layout.addSpacing(theme.SPACING)
        layout.addLayout(button_row)
        self.setLayout(layout)
        self.setStyleSheet(
            f"background-color: {theme.WINDOW_BACKGROUND}; color: {theme.TEXT_PRIMARY};"
        )

    @property
    def automatic_update_checks(self) -> bool:
        return self.automatic_update_checkbox.isChecked()

    @property
    def player_display_name(self) -> str:
        return self.player_display_name_input.text().strip()

    @property
    def coordination_enabled(self) -> bool:
        return self.coordination_enabled_checkbox.isChecked()

    @property
    def coordination_server_url(self) -> str:
        return self.coordination_server_input.text().strip()

    @property
    def coordination_device_name(self) -> str:
        return self.coordination_device_name_input.text().strip()

    @property
    def coordination_pairing_code(self) -> str:
        return self.coordination_pairing_code_input.text().strip()

    def _request_check(self) -> None:
        self.check_requested = True
        self.accept()

    def _coordination_enabled_changed(self, enabled: bool) -> None:
        for control in (
            self.coordination_server_input,
            self.coordination_device_name_input,
            self.coordination_pairing_code_input,
        ):
            control.setEnabled(enabled)

        if not enabled:
            status = (
                "Status: Disabled. Project cards use local protection only."
            )
        elif self._paired_device_id:
            status = f"Status: Paired device {self._paired_device_id}"
        else:
            status = "Status: Not paired. Enter the pairing code before saving."

        self.coordination_status_label.setText(status)
