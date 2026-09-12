import platform

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.settings import AppSettings
from app.core.distribution import DistributionChannel, detect_distribution_channel
from app.ui import styles, theme
from app.version import APP_VERSION


class SettingsDialog(QDialog):
    ACTION_CREATE_GROUP = "create_group"
    ACTION_JOIN_GROUP = "join_group"
    ACTION_CREATE_INVITATION = "create_invitation"
    ACTION_MANAGE_DEVICES = "manage_devices"
    ACTION_CLAIM_ADMINISTRATOR = "claim_administrator"
    ACTION_LEAVE_GROUP = "leave_group"
    ACTION_SWITCH_GROUP = "switch_group"

    def __init__(
        self,
        settings: AppSettings,
        parent=None,
        *,
        distribution_channel: DistributionChannel | None = None,
    ) -> None:
        super().__init__(parent)
        self.distribution_channel = (
            detect_distribution_channel()
            if distribution_channel is None
            else distribution_channel
        )
        self.check_requested = False
        self.coordination_action: str | None = None

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

        self.manual_transfer_checkbox = QCheckBox(
            "Show manual Receive and Hand Off controls"
        )
        self.manual_transfer_checkbox.setChecked(
            settings.manual_transfer_controls
        )
        self.manual_transfer_checkbox.setToolTip(
            "By default, Host receives the latest group version, launches the "
            "game, and hands off after the game closes. Enable this for manual "
            "transfers or troubleshooting."
        )

        journal_heading = QLabel("Session Journal")
        journal_heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        journal_description = QLabel(
            "Save Shift can offer to record accomplishments, discoveries, "
            "or notes for the next host after a hosted session. Entries can "
            "always be added later from the project card."
        )
        journal_description.setWordWrap(True)
        journal_description.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        self.session_journal_prompt_checkbox = QCheckBox(
            "Ask to record a World Journal entry after hosted sessions"
        )
        self.session_journal_prompt_checkbox.setChecked(
            settings.prompt_for_session_journal
        )

        self.update_management_label = QLabel()
        self.update_management_label.setWordWrap(True)
        self.update_management_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY};"
        )

        if self.distribution_channel.updates_managed_externally:
            self.automatic_update_checkbox.setEnabled(False)
            self.automatic_update_checkbox.setVisible(False)
            self.update_management_label.setText(
                "Updates for this installation are downloaded and installed "
                "automatically by Steam."
            )
        else:
            self.update_management_label.setText(
                "Standalone installations receive installer updates from "
                "Save Shift's official GitHub releases."
            )

        coordination_heading = QLabel("Groups & Project Coordination")
        coordination_heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        coordination_description = QLabel(
            "Create or join groups through Steam friends. Existing Cloudflare "
            "groups remain available while Save Shift migrates their shared "
            "worlds and coordination safely."
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
        self._is_administrator = settings.coordination_is_administrator
        active_group = settings.active_coordination_group
        self._provider_kind = (
            active_group.provider_kind
            if active_group is not None
            else settings.coordination_provider_kind
        )

        self.group_selector = QComboBox()
        self.group_selector.setObjectName("CoordinationGroupSelector")
        for group in settings.coordination_groups:
            self.group_selector.addItem(group.name, group.group_id)
        active_index = self.group_selector.findData(
            settings.active_coordination_group_id
        )
        if active_index >= 0:
            self.group_selector.setCurrentIndex(active_index)
        self.switch_group_button = QPushButton("Switch")
        self.switch_group_button.setStyleSheet(styles.secondary_button_style())
        self.switch_group_button.clicked.connect(
            lambda: self._request_coordination_action(self.ACTION_SWITCH_GROUP)
        )
        group_row = QHBoxLayout()
        group_row.addWidget(self.group_selector, 1)
        group_row.addWidget(self.switch_group_button)

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

        self.create_group_button = QPushButton("Create Group")
        self.create_group_button.setStyleSheet(styles.primary_button_style())
        self.create_group_button.clicked.connect(
            lambda: self._request_coordination_action(self.ACTION_CREATE_GROUP)
        )
        self.create_group_button.setEnabled(True)

        self.join_group_button = QPushButton("Join Group")
        self.join_group_button.setStyleSheet(styles.secondary_button_style())
        self.join_group_button.clicked.connect(
            lambda: self._request_coordination_action(self.ACTION_JOIN_GROUP)
        )

        self.create_invitation_button = QPushButton("Invite a Friend")
        self.create_invitation_button.setStyleSheet(styles.primary_button_style())
        self.create_invitation_button.clicked.connect(
            lambda: self._request_coordination_action(
                self.ACTION_CREATE_INVITATION
            )
        )

        self.manage_devices_button = QPushButton("Manage Computers")
        self.manage_devices_button.setStyleSheet(styles.secondary_button_style())
        self.manage_devices_button.clicked.connect(
            lambda: self._request_coordination_action(self.ACTION_MANAGE_DEVICES)
        )

        self.claim_administrator_button = QPushButton("Claim Administrator")
        self.claim_administrator_button.setStyleSheet(
            styles.secondary_button_style()
        )
        self.claim_administrator_button.clicked.connect(
            lambda: self._request_coordination_action(
                self.ACTION_CLAIM_ADMINISTRATOR
            )
        )

        self.leave_group_button = QPushButton("Leave Group")
        self.leave_group_button.setStyleSheet(styles.secondary_button_style())
        self.leave_group_button.clicked.connect(
            lambda: self._request_coordination_action(self.ACTION_LEAVE_GROUP)
        )

        coordination_setup_row = QHBoxLayout()
        coordination_setup_row.addWidget(self.create_group_button)
        coordination_setup_row.addWidget(self.join_group_button)
        coordination_setup_row.addStretch()

        coordination_management_row = QHBoxLayout()
        coordination_management_row.addWidget(self.create_invitation_button)
        coordination_management_row.addWidget(self.manage_devices_button)
        coordination_management_row.addWidget(self.claim_administrator_button)
        coordination_management_row.addWidget(self.leave_group_button)
        coordination_management_row.addStretch()

        self.coordination_setup_note = QLabel()
        self.coordination_setup_note.setWordWrap(True)
        self.coordination_setup_note.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY};"
        )

        if not self._paired_device_id:
            self.coordination_setup_note.setText(
                "New groups use Steam identity, friend invitations, and signed "
                "Workshop data. Custom provider settings below are retained "
                "for existing groups."
            )

        paired = bool(self._paired_device_id)
        self.create_group_button.setVisible(True)
        self.join_group_button.setVisible(True)
        self.create_invitation_button.setVisible(
            paired and self._is_administrator
        )
        self.manage_devices_button.setVisible(
            paired and self._is_administrator and self._provider_kind != "steam"
        )
        self.claim_administrator_button.setVisible(False)
        self.leave_group_button.setVisible(paired)

        self.advanced_coordination_checkbox = QCheckBox(
            "Advanced custom provider setup"
        )
        self.advanced_coordination_checkbox.toggled.connect(
            self._advanced_coordination_changed
        )
        self._coordination_form = coordination_form
        self._advanced_coordination_changed(False)

        self.check_now_button = QPushButton("Check for Updates")
        self.check_now_button.setStyleSheet(styles.secondary_button_style())
        self.check_now_button.clicked.connect(self._request_check)
        self.check_now_button.setVisible(
            not self.distribution_channel.updates_managed_externally
        )

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
        layout.addWidget(self.update_management_label)
        layout.addSpacing(theme.SPACING)
        layout.addWidget(journal_heading)
        layout.addWidget(journal_description)
        layout.addWidget(self.session_journal_prompt_checkbox)
        layout.addSpacing(theme.SPACING)
        layout.addWidget(coordination_heading)
        layout.addWidget(coordination_description)
        if self.group_selector.count():
            layout.addWidget(QLabel("Active group"))
            layout.addLayout(group_row)
        layout.addWidget(self.coordination_enabled_checkbox)
        layout.addLayout(coordination_setup_row)
        layout.addLayout(coordination_management_row)
        layout.addWidget(self.coordination_setup_note)
        layout.addWidget(self.advanced_coordination_checkbox)
        layout.addLayout(coordination_form)
        layout.addWidget(self.coordination_status_label)
        layout.addWidget(self.manual_transfer_checkbox)
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
    def prompt_for_session_journal(self) -> bool:
        return self.session_journal_prompt_checkbox.isChecked()

    @property
    def manual_transfer_controls(self) -> bool:
        return self.manual_transfer_checkbox.isChecked()

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

    @property
    def selected_group_id(self) -> str:
        value = self.group_selector.currentData()
        return value if isinstance(value, str) else ""

    def _request_check(self) -> None:
        self.check_requested = True
        self.accept()

    def _request_coordination_action(self, action: str) -> None:
        self.coordination_action = action
        self.accept()

    def _advanced_coordination_changed(self, visible: bool) -> None:
        for field in (
            self.coordination_server_input,
            self.coordination_device_name_input,
            self.coordination_pairing_code_input,
        ):
            field.setVisible(visible)
            label = self._coordination_form.labelForField(field)

            if label is not None:
                label.setVisible(visible)

        self.claim_administrator_button.setVisible(
            visible and bool(self._paired_device_id) and not self._is_administrator
        )

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
            role = "group administrator" if self._is_administrator else "group member"
            if self._provider_kind == "steam":
                status = f"Status: Connected through Steam as a {role}."
            else:
                status = f"Status: Connected as a {role}."
        else:
            status = (
                "Status: Not paired with an active group. Create one or join "
                "through a Steam friend."
            )

        self.coordination_status_label.setText(status)
