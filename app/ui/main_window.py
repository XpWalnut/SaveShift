from contextlib import contextmanager
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime
import os
import platform
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_repository import ProjectRepository
from app.core.logging import logger
from app.core.distribution import detect_distribution_channel
from app.core.settings import AppSettings, SettingsService
from app.coordination.errors import (
    CoordinationConfigurationError,
    CoordinationError,
    CoordinationUnavailableError,
    LockConflictError,
    LockOwnershipError,
)
from app.coordination.http_provider import HttpCoordinationProvider
from app.coordination.manager import CoordinationManager
from app.coordination.models import (
    CatalogPackage,
    GroupInvitation,
    LockLease,
    PairedDevice,
)
from app.coordination.cloudflare_provisioning import CreatedGroup
from app.coordination.setup_controller import GroupLeaveOutcome, GroupSetupController
from app.coordination.status_controller import LockStatusController
from app.package_transport.controller import PackageHandoffController
from app.games.registry import GameRegistry
from app.services.export_service import ExportService
from app.services.restore_service import RestoreService
from app.services.hosting_service import HostingService
from app.services.import_service import ImportService
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.services.project_version_service import ProjectVersionService
from app.services.session_journal_service import SessionJournalService
from app.ui import styles, theme
from app.ui.widgets.installed_game_card import InstalledGameCard
from app.ui.widgets.project_card import ProjectCard
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.dialogs.getting_started_dialog import GettingStartedDialog
from app.ui.dialogs.journal_entry_dialog import JournalEntryDialog
from app.ui.dialogs.import_conflict_dialog import ImportConflictDialog
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.dialogs.shared_projects_dialog import SharedProjectsDialog
from app.ui.dialogs.update_dialog import UpdateAvailableDialog
from app.updates.controller import UpdateController
from app.updates.models import UpdateRelease
from app.updates.service import UpdateService


def discover_all_projects() -> None:
    for installed_game in InstalledGameService.get_installed_games():
        try:
            ProjectService.discover_projects(installed_game.id)
        except Exception:
            continue


class MainWindow(QMainWindow):
    def __init__(
            self,
            startup_package_path: Path | None = None,
    ) -> None:
        super().__init__()

        self.setWindowTitle("Save Shift")
        self.setMinimumSize(950, 650)

        self.startup_package_path = startup_package_path
        self.distribution_channel = detect_distribution_channel()
        self.settings = SettingsService.load()
        self.coordination_manager = self._create_coordination_manager(
            self.settings
        )
        self.coordination_renewal_timer = QTimer(self)
        self.coordination_renewal_timer.setInterval(5 * 60 * 1000)
        self.coordination_renewal_timer.timeout.connect(
            self._renew_coordination_leases
        )
        self.lock_status_controller = LockStatusController(self)
        self.lock_status_controller.completed.connect(
            self._lock_statuses_loaded
        )
        self.lock_status_controller.failed.connect(
            self._lock_statuses_failed
        )
        self.lock_status_timer = QTimer(self)
        self.lock_status_timer.setInterval(30 * 1000)
        self.lock_status_timer.timeout.connect(
            self._refresh_project_lock_statuses
        )
        self.project_cards: dict[str, ProjectCard] = {}
        self.project_lock_statuses: dict[str, LockLease | None] = {}
        self.group_setup_controller = GroupSetupController(self)
        self.group_setup_controller.create_completed.connect(
            self._group_created
        )
        self.group_setup_controller.join_completed.connect(
            self._group_joined
        )
        self.group_setup_controller.leave_completed.connect(
            self._group_left
        )
        self.group_setup_controller.failed.connect(
            self._group_setup_failed
        )
        self._group_setup_progress: QProgressDialog | None = None
        self._pending_coordination_profile_name = ""
        self._pending_coordination_device_name = ""
        self._leaving_group = False
        self.package_handoff_controller = PackageHandoffController(self)
        self.package_handoff_controller.publish_completed.connect(
            self._group_handoff_published
        )
        self.package_handoff_controller.download_completed.connect(
            self._group_package_downloaded
        )
        self.package_handoff_controller.catalog_completed.connect(
            self._shared_projects_loaded
        )
        self.package_handoff_controller.legal_agreement_required.connect(
            self._open_workshop_agreement
        )
        self.package_handoff_controller.failed.connect(
            self._group_handoff_failed
        )
        self._package_handoff_progress: QProgressDialog | None = None
        self._pending_handoff_project: Project | None = None
        self._pending_handoff_version: ProjectVersion | None = None
        self._pending_receive_project: Project | None = None
        self._pending_receive_project_name = ""
        self._listing_shared_projects = False

        if self.coordination_manager is not None:
            self.coordination_renewal_timer.start()
            self.lock_status_timer.start()

        self.update_controller = UpdateController(self)
        self.update_controller.update_available.connect(
            self._update_available
        )
        self.update_controller.no_update_available.connect(
            self._no_update_available
        )
        self.update_controller.check_failed.connect(
            self._update_check_failed
        )
        self.update_controller.download_progress.connect(
            self._update_download_progress
        )
        self.update_controller.download_completed.connect(
            self._update_download_completed
        )
        self.update_controller.download_failed.connect(
            self._update_download_failed
        )
        self.update_progress_dialog: QProgressDialog | None = None

        self.selected_installed_game_id: int | None = None

        self.title = QLabel("Save Shift")
        self.title.setStyleSheet("font-size: 28px; font-weight: bold;")

        self.subtitle = QLabel("Seamlessly hand off self-hosted co-op game worlds between friends.")
        self.subtitle.setStyleSheet(f"font-size: 14px; color: {theme.TEXT_SECONDARY};")

        self.installed_game_heading = QLabel("Installed Games")
        self.project_heading = QLabel("Projects")

        self.installed_game_scroll = QScrollArea()
        self.installed_game_scroll.setWidgetResizable(True)
        self.installed_game_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.installed_game_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.installed_game_scroll.setMinimumHeight(220)
        self.installed_game_scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            """
        )

        self.installed_game_container = QWidget()
        self.installed_game_layout = QVBoxLayout()
        self.installed_game_layout.setContentsMargins(
            0,
            0,
            theme.SPACING,
            0,
        )
        self.installed_game_layout.setSpacing(theme.SPACING)
        self.installed_game_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.installed_game_container.setLayout(
            self.installed_game_layout
        )

        self.installed_game_scroll.setWidget(
            self.installed_game_container
        )

        self.project_scroll = QScrollArea()
        self.project_scroll.setWidgetResizable(True)
        self.project_scroll.setStyleSheet("""
        QScrollArea {
            border: none;
            background: transparent;
        }
        """)

        self.project_container = QWidget()
        self.project_layout = QVBoxLayout()
        self.project_layout.setSpacing(theme.SPACING)
        self.project_container.setLayout(self.project_layout)
        self.project_scroll.setWidget(self.project_container)

        self.add_button = QPushButton("Add Game")
        self.add_button.clicked.connect(self.add_installed_game)

        self.detect_games_button = QPushButton("Detect Steam Games")
        self.detect_games_button.clicked.connect(self.detect_steam_games)

        self.remove_button = QPushButton("Remove Game")
        self.remove_button.clicked.connect(self.remove_selected_game)

        self.create_group_button = QPushButton("Create Group")
        self.create_group_button.clicked.connect(self.create_group_from_home)

        self.join_group_button = QPushButton("Join Group")
        self.join_group_button.clicked.connect(self.join_group_from_home)

        self.invite_friend_button = QPushButton("Invite a Friend")
        self.invite_friend_button.clicked.connect(self._create_group_invitation)

        self.shared_projects_button = QPushButton("Receive Shared World")
        self.shared_projects_button.clicked.connect(self.show_shared_projects)

        self.how_it_works_button = QPushButton("How It Works")
        self.how_it_works_button.clicked.connect(self.show_getting_started)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.show_settings)


        for button in (
            self.add_button,
            self.detect_games_button,
            self.remove_button,
            self.create_group_button,
            self.join_group_button,
            self.invite_friend_button,
            self.shared_projects_button,
            self.how_it_works_button,
            self.settings_button,
        ):
            button.setStyleSheet(styles.secondary_button_style())

        left_panel = QVBoxLayout()
        left_panel.addWidget(self.installed_game_heading)
        left_panel.addWidget(self.installed_game_scroll, 1)
        left_panel.addSpacing(theme.SPACING)
        left_panel.addWidget(self.add_button)
        left_panel.addWidget(self.detect_games_button)
        left_panel.addWidget(self.remove_button)
        left_panel.addWidget(self.create_group_button)
        left_panel.addWidget(self.join_group_button)
        left_panel.addWidget(self.invite_friend_button)
        left_panel.addWidget(self.shared_projects_button)
        left_panel.addWidget(self.how_it_works_button)
        left_panel.addWidget(self.settings_button)
        left_panel.addStretch()

        left_container = QWidget()
        left_container.setLayout(left_panel)

        right_panel = QVBoxLayout()
        right_panel.addWidget(self.project_heading)
        right_panel.addWidget(self.project_scroll)

        right_container = QWidget()
        right_container.setLayout(right_panel)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(theme.SPACING_LARGE)
        content_layout.addWidget(left_container)
        content_layout.addWidget(right_container)
        content_layout.setStretch(0, 2)
        content_layout.setStretch(1, 7)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(theme.SPACING)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addSpacing(theme.SPACING)
        layout.addLayout(content_layout)

        container = QWidget()
        container.setLayout(layout)
        container.setStyleSheet(f"background-color: {theme.WINDOW_BACKGROUND};")
        self.setCentralWidget(container)

        discover_all_projects()
        self.load_installed_games()
        self.load_projects()
        self._refresh_group_buttons()
        QTimer.singleShot(0, self._start_automatic_game_detection)

        if startup_package_path is not None:
            QTimer.singleShot(
                0,
                lambda: self.import_package(startup_package_path),
            )
        else:
            QTimer.singleShot(0, self._start_automatic_update_check)

    def show_getting_started(self) -> None:
        GettingStartedDialog(self).exec()

    def _start_automatic_game_detection(self) -> None:
        if os.environ.get("SAVESHIFT_DISABLE_GAME_DETECTION") == "1":
            return
        if InstalledGameService.get_installed_games():
            return

        self._detect_steam_games(show_messages=False)

    def _coordination_identity(self) -> tuple[str, str] | None:
        profile_name = self.settings.player_display_name.strip()
        if not profile_name:
            profile_name, accepted = QInputDialog.getText(
                self,
                "Your Display Name",
                "What name should your friends see?",
            )
            profile_name = profile_name.strip()
            if not accepted or not profile_name:
                return None

        device_name = (
            self.settings.coordination_device_name.strip()
            or platform.node().strip()
            or "Windows PC"
        )
        return device_name, profile_name

    def create_group_from_home(self) -> None:
        identity = self._coordination_identity()
        if identity is not None:
            self._begin_create_group(*identity)

    def join_group_from_home(self) -> None:
        identity = self._coordination_identity()
        if identity is not None:
            self._begin_join_group(*identity)

    def _refresh_group_buttons(self) -> None:
        connected = self.settings.coordination_enabled
        self.create_group_button.setVisible(not connected)
        self.join_group_button.setVisible(not connected)
        self.invite_friend_button.setVisible(
            connected and self.settings.coordination_is_administrator
        )
        self.shared_projects_button.setVisible(connected)

        self.detect_games_button.setToolTip(
            "Scan every Steam library for supported installed games, including "
            "games that do not have a save yet."
        )
        self.create_group_button.setToolTip(
            "Create a private group and become its administrator."
        )
        self.join_group_button.setToolTip(
            "Paste a single-use invitation from a friend. Save Shift will then "
            "detect games and check for shared worlds automatically."
        )
        self.invite_friend_button.setToolTip(
            "Copy a single-use invitation that you can send to one friend."
        )
        self.shared_projects_button.setToolTip(
            "Check this group for worlds that have not been added to this computer."
        )
        self.how_it_works_button.setToolTip(
            "Learn the Receive, Host, play, and Hand Off workflow."
        )

    def show_settings(self) -> None:
        dialog = SettingsDialog(
            settings=self.settings,
            parent=self,
            distribution_channel=self.distribution_channel,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        coordination_action = getattr(dialog, "coordination_action", None)

        if coordination_action == "create_group":
            self._begin_create_group(
                dialog.coordination_device_name,
                dialog.player_display_name,
            )
            return

        if coordination_action == "join_group":
            self._begin_join_group(
                dialog.coordination_device_name,
                dialog.player_display_name,
            )
            return

        if coordination_action == "create_invitation":
            self._create_group_invitation()
            return

        if coordination_action == "manage_devices":
            self._manage_group_devices()
            return

        if coordination_action == "claim_administrator":
            self._claim_group_administrator(dialog.coordination_pairing_code)
            return

        if coordination_action == "leave_group":
            self._begin_leave_group()
            return

        if (
            self.coordination_manager is not None
            and self.coordination_manager.active_leases
            and (
                not dialog.coordination_enabled
                or dialog.coordination_server_url
                != self.settings.coordination_server_url
            )
        ):
            QMessageBox.warning(
                self,
                "Project Lock Active",
                (
                    "Export the hosted project or close Save Shift before "
                    "disabling or changing its coordination provider."
                ),
            )
            return

        candidate = replace(
            self.settings,
            automatic_update_checks=dialog.automatic_update_checks,
            player_display_name=dialog.player_display_name,
            coordination_enabled=dialog.coordination_enabled,
            coordination_server_url=dialog.coordination_server_url,
            coordination_device_name=dialog.coordination_device_name,
        )

        if candidate.coordination_enabled:
            if not candidate.coordination_server_url:
                QMessageBox.warning(
                    self,
                    "Provider URL Required",
                    "Enter the HTTPS URL for the coordination provider.",
                )
                return

            if not candidate.coordination_device_name:
                QMessageBox.warning(
                    self,
                    "Computer Name Required",
                    "Enter a name for this computer.",
                )
                return

            provider_changed = (
                candidate.coordination_server_url
                != self.settings.coordination_server_url
            )

            if provider_changed:
                candidate = replace(
                    candidate,
                    coordination_is_administrator=False,
                    coordination_provider_kind="custom",
                    coordination_cloudflare_account_id="",
                    coordination_cloudflare_script_name="",
                )
            needs_pairing = (
                provider_changed
                or not candidate.coordination_device_token
                or bool(dialog.coordination_pairing_code)
            )

            if needs_pairing:
                if not dialog.coordination_pairing_code:
                    QMessageBox.warning(
                        self,
                        "Pairing Code Required",
                        (
                            "Enter the provider pairing code to connect "
                            "this computer."
                        ),
                    )
                    return

                try:
                    provider = HttpCoordinationProvider(
                        candidate.coordination_server_url
                    )
                    device = provider.pair(
                        pairing_code=dialog.coordination_pairing_code,
                        device_name=candidate.coordination_device_name,
                    )
                except CoordinationError as error:
                    QMessageBox.warning(
                        self,
                        "Pairing Failed",
                        f"Save Shift could not pair this computer.\n\n{error}",
                    )
                    return

                candidate = replace(
                    candidate,
                    coordination_device_id=device.device_id,
                    coordination_device_token=device.device_token,
                    coordination_is_administrator=device.administrator,
                )

        try:
            SettingsService.save(candidate)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Settings Not Saved",
                f"Save Shift could not save its settings.\n\n{error}",
            )
            return

        self.settings = candidate
        self.coordination_manager = self._create_coordination_manager(
            self.settings
        )
        self.project_lock_statuses.clear()

        if self.coordination_manager is not None:
            self.coordination_renewal_timer.start()
            self.lock_status_timer.start()
        else:
            self.coordination_renewal_timer.stop()
            self.lock_status_timer.stop()

        self.load_projects()

        if dialog.check_requested:
            self.check_for_updates(manual=True)

    def _begin_create_group(
        self,
        device_name: str,
        profile_name: str,
    ) -> None:
        if not device_name:
            QMessageBox.warning(
                self,
                "Computer Name Required",
                "Enter a name for this computer before creating a group.",
            )
            return

        self._pending_coordination_profile_name = profile_name
        self._pending_coordination_device_name = device_name
        self._show_group_setup_progress(
            "Sign in to Cloudflare in your browser. Save Shift will create "
            "and verify the group automatically."
        )

        if not self.group_setup_controller.create_group(device_name):
            self._close_group_setup_progress()

    def _begin_join_group(
        self,
        device_name: str,
        profile_name: str,
    ) -> None:
        if not device_name:
            QMessageBox.warning(
                self,
                "Computer Name Required",
                "Enter a name for this computer before joining a group.",
            )
            return
        invitation_text, accepted = QInputDialog.getMultiLineText(
            self,
            "Join Save Shift Group",
            "Paste the invitation from your friend:",
        )

        if not accepted:
            return

        try:
            invitation = GroupInvitation.from_text(invitation_text)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Invitation", str(error))
            return

        if invitation.expires_at_utc <= datetime.now(UTC):
            QMessageBox.warning(
                self,
                "Invitation Expired",
                "Ask the group administrator to create another invitation.",
            )
            return

        self._pending_coordination_profile_name = profile_name
        self._pending_coordination_device_name = device_name
        self._show_group_setup_progress("Connecting this computer to the group…")

        if not self.group_setup_controller.join_group(invitation, device_name):
            self._close_group_setup_progress()

    def _group_created(self, created: CreatedGroup) -> None:
        self._close_group_setup_progress()
        settings = replace(
            self.settings,
            player_display_name=self._pending_coordination_profile_name,
            coordination_enabled=True,
            coordination_server_url=created.provider_url,
            coordination_device_id=created.device.device_id,
            coordination_device_name=self._pending_coordination_device_name,
            coordination_device_token=created.device.device_token,
            coordination_is_administrator=True,
            coordination_provider_kind="cloudflare",
            coordination_cloudflare_account_id=created.account_id,
            coordination_cloudflare_script_name=created.script_name,
        )
        if not self._apply_coordination_settings(settings):
            return
        QMessageBox.information(
            self,
            "Group Created",
            "Your group is ready. Choose Invite a Friend on the main screen "
            "to connect another computer.",
        )
        self._detect_steam_games(show_messages=False)

    def _group_joined(
        self,
        invitation: GroupInvitation,
        device: PairedDevice,
    ) -> None:
        self._close_group_setup_progress()
        settings = replace(
            self.settings,
            player_display_name=self._pending_coordination_profile_name,
            coordination_enabled=True,
            coordination_server_url=invitation.provider_url,
            coordination_device_id=device.device_id,
            coordination_device_name=self._pending_coordination_device_name,
            coordination_device_token=device.device_token,
            coordination_is_administrator=device.administrator,
            coordination_provider_kind="",
            coordination_cloudflare_account_id="",
            coordination_cloudflare_script_name="",
        )
        if not self._apply_coordination_settings(settings):
            return
        QMessageBox.information(
            self,
            "Group Joined",
            "This computer is now connected. Save Shift will detect supported "
            "Steam games and check the group for shared worlds next.",
        )
        self._detect_steam_games(show_messages=False)
        self.show_shared_projects()

    def _begin_leave_group(self) -> None:
        if self.coordination_manager is not None and self.coordination_manager.active_leases:
            QMessageBox.warning(
                self,
                "Project Lock Active",
                "Export the hosted project or close the game before leaving the group.",
            )
            return

        owner_cleanup = bool(
            self.settings.coordination_provider_kind == "cloudflare"
            and self.settings.coordination_cloudflare_account_id
            and self.settings.coordination_cloudflare_script_name
        )
        detail = (
            " If this is the final computer, your browser will open so Save Shift "
            "can remove the provider from your Cloudflare account."
            if owner_cleanup
            else ""
        )
        confirmed = QMessageBox.question(
            self,
            "Leave Group",
            "Remove this computer from the Save Shift group?" + detail,
        )

        if confirmed != QMessageBox.StandardButton.Yes:
            return

        self._show_group_setup_progress("Removing this computer from the group…")
        started = self.group_setup_controller.leave_group(
            self.settings.coordination_server_url,
            self.settings.coordination_device_token,
            account_id=(
                self.settings.coordination_cloudflare_account_id
                if owner_cleanup
                else ""
            ),
            script_name=(
                self.settings.coordination_cloudflare_script_name
                if owner_cleanup
                else ""
            ),
        )

        if not started:
            self._close_group_setup_progress()
            return

        self._leaving_group = True

    def _group_left(self, outcome: GroupLeaveOutcome) -> None:
        self._close_group_setup_progress()
        self._leaving_group = False

        if not self._clear_local_group_settings():
            return

        if outcome.cleanup_warning:
            QMessageBox.warning(
                self,
                "Group Left",
                "This computer left the group and its remote group data was cleared, "
                "but Save Shift could not remove the Worker from Cloudflare. Delete "
                "the Worker from the Cloudflare dashboard when convenient.\n\n"
                f"{outcome.cleanup_warning}",
            )
            return

        message = "This computer is no longer connected to the group."
        if outcome.cloudflare_worker_removed:
            message = "The empty group and its Cloudflare provider were removed."
        elif outcome.group_empty:
            message = "The final computer left and the group data was removed."

        QMessageBox.information(self, "Group Left", message)

    def _clear_local_group_settings(self) -> bool:
        settings = replace(
            self.settings,
            coordination_enabled=False,
            coordination_server_url="",
            coordination_device_id="",
            coordination_device_name="",
            coordination_device_token="",
            coordination_is_administrator=False,
            coordination_provider_kind="",
            coordination_cloudflare_account_id="",
            coordination_cloudflare_script_name="",
        )
        return self._apply_coordination_settings(settings)

    def _group_setup_failed(self, message: str) -> None:
        self._close_group_setup_progress()
        was_leaving = self._leaving_group
        self._leaving_group = False

        if was_leaving and not self.settings.coordination_is_administrator:
            confirmed = QMessageBox.question(
                self,
                "Could Not Contact Group",
                "Save Shift could not remove this computer from the provider. "
                "Forget the group on this computer anyway? The group administrator "
                "can revoke this computer later.\n\n"
                f"{message}",
            )

            if confirmed == QMessageBox.StandardButton.Yes:
                if self._clear_local_group_settings():
                    QMessageBox.information(
                        self,
                        "Group Forgotten",
                        "This computer is no longer configured to use the group.",
                    )
                return

        QMessageBox.warning(
            self,
            "Group Operation Failed",
            message or "Save Shift could not finish the group operation.",
        )

    def _show_group_setup_progress(self, message: str) -> None:
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle("Save Shift Group Setup")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self._group_setup_progress = progress

    def _close_group_setup_progress(self) -> None:
        if self._group_setup_progress is not None:
            self._group_setup_progress.close()
            self._group_setup_progress.deleteLater()
            self._group_setup_progress = None

    def _apply_coordination_settings(self, settings: AppSettings) -> bool:
        try:
            SettingsService.save(settings)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Settings Error",
                f"Save Shift could not save the group settings.\n\n{error}",
            )
            return False

        self.settings = settings
        self.coordination_manager = self._create_coordination_manager(settings)

        if self.coordination_manager is not None:
            self.coordination_renewal_timer.start()
            self.lock_status_timer.start()
            self._refresh_project_lock_statuses()
        else:
            self.coordination_renewal_timer.stop()
            self.lock_status_timer.stop()

        self.load_projects()
        self._refresh_group_buttons()
        return True

    def _create_group_invitation(self) -> None:
        if not self.settings.coordination_is_administrator:
            QMessageBox.warning(
                self,
                "Administrator Required",
                "Only the group administrator can create invitations.",
            )
            return

        try:
            provider = HttpCoordinationProvider(
                self.settings.coordination_server_url,
                device_token=self.settings.coordination_device_token,
            )
            invitation = provider.create_invitation()
        except CoordinationError as error:
            QMessageBox.warning(self, "Invitation Failed", str(error))
            return

        invitation_text = invitation.to_text()
        QApplication.clipboard().setText(invitation_text)
        QMessageBox.information(
            self,
            "Invitation Copied",
            "A single-use invitation valid for 24 hours was copied to the "
            "clipboard. Send it to one friend through a trusted channel.",
        )

    def _manage_group_devices(self) -> None:
        if not self.settings.coordination_is_administrator:
            QMessageBox.warning(
                self,
                "Administrator Required",
                "Only the group administrator can manage computers.",
            )
            return

        provider = HttpCoordinationProvider(
            self.settings.coordination_server_url,
            device_token=self.settings.coordination_device_token,
        )

        try:
            devices = provider.list_devices()
        except CoordinationError as error:
            QMessageBox.warning(self, "Computer List Failed", str(error))
            return

        candidates = [
            device
            for device in devices
            if not device.revoked
            and device.device_id != self.settings.coordination_device_id
        ]

        if not candidates:
            QMessageBox.information(
                self,
                "Group Computers",
                "There are no other active computers to revoke.",
            )
            return

        labels = [
            f"{device.device_name} — paired {device.created_at_utc:%Y-%m-%d}"
            for device in candidates
        ]
        selected, accepted = QInputDialog.getItem(
            self,
            "Manage Group Computers",
            "Choose a computer to revoke:",
            labels,
            0,
            False,
        )

        if not accepted:
            return

        target = candidates[labels.index(selected)]
        confirmed = QMessageBox.question(
            self,
            "Revoke Computer",
            f"Revoke {target.device_name}? It will need a new invitation to reconnect.",
        )

        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            provider.revoke_device(target.device_id)
        except CoordinationError as error:
            QMessageBox.warning(self, "Revocation Failed", str(error))
            return

        QMessageBox.information(
            self,
            "Computer Revoked",
            f"{target.device_name} can no longer use this group.",
        )

    def _claim_group_administrator(self, pairing_code: str) -> None:
        if self.settings.coordination_is_administrator:
            return

        if not pairing_code:
            QMessageBox.warning(
                self,
                "Pairing Code Required",
                "Enter the provider's existing pairing code first.",
            )
            return

        provider = HttpCoordinationProvider(
            self.settings.coordination_server_url,
            device_token=self.settings.coordination_device_token,
        )

        try:
            provider.claim_administrator(pairing_code)
        except CoordinationError as error:
            QMessageBox.warning(
                self,
                "Administrator Migration Failed",
                str(error),
            )
            return

        settings = replace(
            self.settings,
            coordination_is_administrator=True,
        )

        if not self._apply_coordination_settings(settings):
            return

        QMessageBox.information(
            self,
            "Administrator Access Enabled",
            "This computer can now invite friends and manage group computers.",
        )

    def check_for_updates(self, *, manual: bool = True) -> None:
        if self.distribution_channel.updates_managed_externally:
            if manual:
                QMessageBox.information(
                    self,
                    "Updates Managed by Steam",
                    "Steam automatically downloads and installs updates for "
                    "this Save Shift installation.",
                )
            return

        started = self.update_controller.check_for_updates(manual=manual)

        if started:
            self.statusBar().showMessage("Checking for Save Shift updates…")
            return

        if manual:
            QMessageBox.information(
                self,
                "Update Check in Progress",
                "Save Shift is already checking for updates.",
            )

    def _start_automatic_update_check(self) -> None:
        if self.distribution_channel.updates_managed_externally:
            return

        if os.environ.get("SAVESHIFT_DISABLE_UPDATE_CHECKS") == "1":
            return

        if self.startup_package_path is not None:
            return

        if not self.settings.automatic_update_checks:
            return

        self.check_for_updates(manual=False)

    def _update_available(
        self,
        release: UpdateRelease,
        _manual: bool,
    ) -> None:
        self.statusBar().clearMessage()
        dialog = UpdateAvailableDialog(
            release=release,
            automatic_update_checks=self.settings.automatic_update_checks,
            parent=self,
        )
        result = dialog.exec()
        self.settings = replace(
            self.settings,
            automatic_update_checks=dialog.automatic_update_checks,
        )
        SettingsService.save(self.settings)

        if result != QDialog.DialogCode.Accepted:
            return

        self._begin_update_download(release)

    def _no_update_available(self, manual: bool) -> None:
        self.statusBar().clearMessage()

        if manual:
            QMessageBox.information(
                self,
                "No Updates Available",
                "You are using the latest available version of Save Shift.",
            )

    def _update_check_failed(self, message: str, manual: bool) -> None:
        self.statusBar().clearMessage()

        if manual:
            QMessageBox.warning(
                self,
                "Update Check Failed",
                message,
            )
            return

        logger.warning("Automatic update check failed: %s", message)

    def _begin_update_download(self, release: UpdateRelease) -> None:
        progress_dialog = QProgressDialog(
            f"Downloading Save Shift {release.version}…",
            "",
            0,
            100,
            self,
        )
        progress_dialog.setWindowTitle("Downloading Update")
        progress_dialog.setCancelButton(None)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        self.update_progress_dialog = progress_dialog

        if self.update_controller.download_update(release):
            progress_dialog.show()
            return

        progress_dialog.close()
        self.update_progress_dialog = None
        QMessageBox.information(
            self,
            "Update Download in Progress",
            "Save Shift is already downloading an update.",
        )

    def _update_download_progress(self, progress: int) -> None:
        if self.update_progress_dialog is not None:
            self.update_progress_dialog.setValue(progress)

    def _update_download_completed(self, installer_path: Path) -> None:
        self._close_update_progress_dialog()

        try:
            UpdateService.launch_installer(Path(installer_path))
        except Exception as error:
            QMessageBox.critical(
                self,
                "Update Launch Failed",
                (
                    "The update was downloaded, but Save Shift could not "
                    f"start the installer.\n\n{error}"
                ),
            )
            return

        self._quit_application()

    def _update_download_failed(self, message: str) -> None:
        self._close_update_progress_dialog()
        QMessageBox.critical(
            self,
            "Update Download Failed",
            (
                f"Save Shift could not download the update.\n\n{message}\n\n"
                "You can continue using the current version."
            ),
        )

    def _close_update_progress_dialog(self) -> None:
        if self.update_progress_dialog is None:
            return

        self.update_progress_dialog.close()
        self.update_progress_dialog = None

    @staticmethod
    def _quit_application() -> None:
        application = QApplication.instance()

        if application is not None:
            application.quit()

    def load_installed_games(self) -> None:
        self._clear_installed_game_cards()

        installed_games = InstalledGameService.get_installed_games()

        if self.selected_installed_game_id is None and installed_games:
            self.selected_installed_game_id = installed_games[0].id

        if self.selected_installed_game_id is not None:
            existing_ids = {game.id for game in installed_games}
            if self.selected_installed_game_id not in existing_ids:
                self.selected_installed_game_id = installed_games[0].id if installed_games else None

        for installed_game in installed_games:
            projects = ProjectService.get_projects_for_installed_game(installed_game.id)

            card = InstalledGameCard(
                installed_game=installed_game,
                project_count=len(projects),
                is_selected=installed_game.id == self.selected_installed_game_id,
            )
            card.selected.connect(self.select_installed_game)

            self.installed_game_layout.addWidget(card)


    def load_projects(self) -> None:
        self.shared_projects_button.setEnabled(
            self.settings.coordination_enabled
            and self.coordination_manager is not None
        )
        self._clear_project_cards()

        selected_game = self._get_selected_installed_game()

        if selected_game is None:
            self.project_heading.setText("Projects")
            empty_label = QLabel("No installed games configured yet.")
            empty_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
            self.project_layout.addWidget(empty_label)
            self.project_layout.addStretch()
            return

        self.project_heading.setText(f"Projects — {selected_game.display_name}")

        projects = ProjectService.get_projects_for_installed_game(selected_game.id)

        if not projects:
            empty_label = QLabel("No projects were found in this game's save folder.")
            empty_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
            self.project_layout.addWidget(empty_label)
            self.project_layout.addStretch()
            return

        for project in projects:
            card = self._create_project_card(
                project=project,
                installed_game=selected_game,
            )
            self.project_cards[project.uuid] = card
            self.project_layout.addWidget(card)

        self.project_layout.addStretch()
        self._refresh_project_lock_statuses()

    def select_installed_game(self, installed_game: InstalledGame) -> None:
        self.selected_installed_game_id = installed_game.id
        self.load_installed_games()
        self.load_projects()

    def add_installed_game(self) -> None:
        configured_game_ids = {
            installed_game.game_id
            for installed_game in InstalledGameService.get_installed_games()
        }

        supported_games = [
            game
            for game in GameRegistry.all()
            if game.game_id not in configured_game_ids
        ]

        if not supported_games:
            QMessageBox.information(
                self,
                "All Games Configured",
                "All currently supported games have already been added.",
            )
            return

        game_names = [
            game.display_name
            for game in supported_games
        ]

        selected_game_name, ok = QInputDialog.getItem(
            self,
            "Add Game",
            "Choose a supported game:",
            game_names,
            0,
            False,
        )

        if not ok or not selected_game_name:
            return

        supported_game = GameRegistry.get_by_display_name(
            selected_game_name
        )

        if supported_game is None:
            QMessageBox.warning(
                self,
                "Unsupported Game",
                "That game is not supported.",
            )
            return

        detected_save_path = supported_game.detect_save_path()

        if detected_save_path is not None:
            use_detected_path = QMessageBox.question(
                self,
                "Default Save Location",
                (
                    f"Save Shift knows the default save location for "
                    f"{supported_game.display_name}:\n\n"
                    f"{detected_save_path}\n\n"
                    "Use this location? The game or a received world will "
                    "create it when needed."
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if use_detected_path == QMessageBox.StandardButton.Yes:
                save_path = str(detected_save_path)
            else:
                save_path = QFileDialog.getExistingDirectory(
                    self,
                    (
                        f"Select the save folder for "
                        f"{supported_game.display_name}"
                    ),
                    str(detected_save_path.parent),
                )
        else:
            QMessageBox.information(
                self,
                "Save Folder Not Found",
                (
                    f"Save Shift could not automatically locate the "
                    f"save folder for {supported_game.display_name}.\n\n"
                    "Please select it manually."
                ),
            )

            save_path = QFileDialog.getExistingDirectory(
                self,
                (
                    f"Select the save folder for "
                    f"{supported_game.display_name}"
                ),
                str(Path.home()),
            )

        if not save_path:
            return

        try:
            installed_game = InstalledGameService.add_installed_game(
                game_id=supported_game.game_id,
                display_name=supported_game.display_name,
                save_path=save_path,
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Game Already Configured",
                str(error),
            )
            return

        self.selected_installed_game_id = installed_game.id

        try:
            ProjectService.discover_projects(installed_game.id)
        except Exception as error:
            QMessageBox.warning(
                self,
                "Game Added",
                (
                    f"{supported_game.display_name} was configured successfully, "
                    "but Save Shift could not discover its projects.\n\n"
                    f"{error}"
                ),
            )

        self.load_installed_games()
        self.load_projects()

    def remove_selected_game(self) -> None:
        if self.selected_installed_game_id is None:
            QMessageBox.information(self, "No Game Selected", "Please select a configured game first.")
            return

        confirm = QMessageBox.question(
            self,
            "Remove Game",
            "Remove this game from Save Shift? This will not delete any save files.",
        )

        if confirm != QMessageBox.Yes:
            return

        InstalledGameService.delete_installed_game(self.selected_installed_game_id)
        self.selected_installed_game_id = None
        self.load_installed_games()
        self.load_projects()


    def host_project(self, project: Project) -> None:
        installed_game = self._get_installed_game_for_project(project)
        player_name = self._get_player_display_name()

        if player_name is None:
            return

        if (
            self.coordination_manager is not None
            and self.coordination_manager.has_active_lease(project.uuid)
        ):
            QMessageBox.information(
                self,
                "Already Hosting",
                (
                    "This computer already owns the project lock. "
                    "Hand it off when you are finished hosting."
                ),
            )
            return

        try:
            self._acquire_hosting_lease(project.uuid, player_name)
        except CoordinationError as error:
            self._show_coordination_error(error)
            return

        logger.info(
            "Starting host session for project %s without creating a new "
            "project version.",
            project.uuid,
        )

        supported_game = GameRegistry.get_by_game_id(
            installed_game.game_id
        )

        if supported_game is None:
            QMessageBox.information(
                self,
                "Project Hosted",
                (
                    "The project is ready to host, but the game could not "
                    "be identified and was not launched automatically.\n\n"
                    "Launch it manually, then use Hand Off when you are "
                    "finished. The next project version will be created "
                    "during handoff."
                ),
            )
            return

        try:
            was_already_running = supported_game.is_running()

            if not was_already_running:
                supported_game.launch()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Project Hosted",
                (
                    "The project is ready to host, but Save Shift could not "
                    "launch "
                    f"{supported_game.display_name} automatically.\n\n"
                    f"{error}\n\n"
                    "You can launch it manually from Steam, then use Hand "
                    "Off when you are finished."
                ),
            )
            return

        if was_already_running:
            launch_message = (
                f"{supported_game.display_name} is already running."
            )
        else:
            launch_message = (
                f"{supported_game.display_name} is launching through Steam."
            )

        QMessageBox.information(
            self,
            "Project Hosted",
            (
                f"{launch_message}\n\n"
                "No new project version was created. Use Hand Off when "
                "you are finished; that will create and share the next "
                "version."
            ),
        )

    def import_package(
            self,
            package_path: Path | None = None,
    ) -> None:
        if package_path is None:
            selected_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Save Shift Package",
                "",
                "Save Shift Packages (*.sspkg)",
            )

            if not selected_path:
                return

            package_path = Path(selected_path)

        try:
            analysis = ImportService.analyze_import(package_path)
        except ValueError as error:
            QMessageBox.warning(self, "Import Not Allowed", str(error))
            return
        except FileNotFoundError as error:
            QMessageBox.critical(self, "Package Not Found", str(error))
            return
        except Exception as error:
            QMessageBox.critical(
                self,
                "Import Failed",
                f"An unexpected error occurred.\n\n{error}",
            )
            return

        conflict_dialog = ImportConflictDialog(analysis, self)

        if conflict_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        package_info = analysis.package_info
        player_name = self._get_player_display_name()

        if player_name is None:
            return

        try:
            with self._temporary_coordination_lease(
                package_info.project_uuid,
                player_name,
            ):
                version = ImportService.import_package(
                    package_path=package_path,
                    imported_by=player_name,
                    allow_replace=analysis.requires_replace_confirmation,
                )
        except CoordinationError as error:
            self._show_coordination_error(error)
            return
        except Exception as error:
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Save Shift could not import this package.\n\n{error}",
            )
            return

        QMessageBox.information(
            self,
            "Package Imported",
            (
                f"Package imported successfully.\n\n"
                f"Version: {version.version_number}\n"
                f"Backup created:\n{version.backup_path}"
            ),
        )

        self.load_installed_games()
        self.load_projects()

    def export_project(self, project: Project) -> None:
        installed_game = self._get_installed_game_for_project(project)
        player_name = self._get_player_display_name()

        if player_name is None:
            return

        suggested_name = f"{project.name}.sspkg"

        destination_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Save Shift Package",
            str(Path.home() / "Desktop" / suggested_name),
            "Save Shift Packages (*.sspkg)",
        )

        if not destination_path:
            return

        destination = Path(destination_path)

        if destination.suffix.lower() != ".sspkg":
            destination = destination.with_suffix(".sspkg")

        journal_title = None
        journal_body = None
        add_journal = QMessageBox.question(
            self,
            "Add to World Journal?",
            (
                "Would you like to record what happened during this session "
                "before handing the world off?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if add_journal == QMessageBox.StandardButton.Yes:
            journal_dialog = JournalEntryDialog(project.name, self)

            if journal_dialog.exec() != QDialog.DialogCode.Accepted:
                return

            journal_title = journal_dialog.entry_title
            journal_body = journal_dialog.entry_body

        lease_acquired_here = False

        try:
            if self.settings.coordination_enabled:
                manager = self._require_coordination_manager()

                if not manager.has_active_lease(project.uuid):
                    self._acquire_hosting_lease(
                        project.uuid,
                        player_name,
                    )
                    lease_acquired_here = True

            version = ExportService.export_project(
                project=project,
                game_id=installed_game.game_id,
                exported_by=player_name,
                destination_path=destination,
                journal_title=journal_title,
                journal_body=journal_body,
                source_device_name=(
                    self.settings.coordination_device_name or None
                ),
            )
        except CoordinationError as error:
            if lease_acquired_here:
                self._release_coordination_lease(
                    project.uuid,
                    report_error=False,
                )
            self._show_coordination_error(error)
            return
        except Exception as error:
            if lease_acquired_here:
                self._release_coordination_lease(
                    project.uuid,
                    report_error=False,
                )
            QMessageBox.critical(
                self,
                "Export Failed",
                (
                    "Save Shift could not export this project.\n\n"
                    f"{error}"
                ),
            )
            return

        release_error = self._release_coordination_lease(
            project.uuid,
            report_error=False,
        )

        QMessageBox.information(
            self,
            "Package Exported",
            (
                f"{project.name} was exported successfully.\n\n"
                f"Version: {version.version_number}\n"
                f"Saved to:\n{destination}"
                + (
                    "\n\nWarning: Save Shift could not release the project "
                    f"lock. It will expire automatically.\n\n{release_error}"
                    if release_error is not None
                    else ""
                )
            ),
        )

        self.load_installed_games()
        self.load_projects()


    def show_history(self, project: Project) -> None:
        dialog = HistoryDialog(
            project=project,
            on_restore=lambda version: self.restore_version(
                project,
                version,
            ),
            on_add_journal=lambda: self.add_journal_entry(project),
            parent=self,
        )
        dialog.exec()

    def show_journal(self, project: Project) -> None:
        dialog = HistoryDialog(
            project=project,
            on_restore=lambda version: self.restore_version(
                project,
                version,
            ),
            on_add_journal=lambda: self.add_journal_entry(project),
            initial_tab="journal",
            parent=self,
        )
        dialog.exec()

    def add_journal_entry(self, project: Project):
        player_name = self._get_player_display_name()

        if player_name is None:
            return None

        dialog = JournalEntryDialog(project.name, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        latest_version = ProjectVersionService.get_latest_version(project.id)

        try:
            entry = SessionJournalService.create_entry(
                project_id=project.id,
                title=dialog.entry_title,
                body=dialog.entry_body,
                created_by=player_name,
                project_version_number=(
                    latest_version.version_number
                    if latest_version is not None
                    else None
                ),
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Journal Entry Not Saved",
                f"Save Shift could not save the journal entry.\n\n{error}",
            )
            return None

        self.load_projects()

        return entry

    def detect_steam_games(self) -> None:
        self._detect_steam_games(show_messages=True)

    def _detect_steam_games(self, *, show_messages: bool) -> list[InstalledGame]:
        try:
            added_games = InstalledGameService.detect_steam_games()
        except Exception as error:
            logger.warning("Automatic Steam game detection failed: %s", error)
            if show_messages:
                QMessageBox.warning(
                    self,
                    "Steam Detection Failed",
                    f"Save Shift could not scan the Steam libraries.\n\n{error}",
                )
            return []

        if not added_games:
            if show_messages:
                QMessageBox.information(
                    self,
                    "No New Games Found",
                    (
                        "Save Shift did not find any unconfigured supported "
                        "games in your Steam libraries."
                    ),
                )
            return []

        discovery_errors: list[str] = []

        for installed_game in added_games:
            try:
                ProjectService.discover_projects(installed_game.id)
            except Exception as error:
                discovery_errors.append(
                    f"{installed_game.display_name}: {error}"
                )

        self.selected_installed_game_id = added_games[0].id
        self.load_installed_games()
        self.load_projects()
        self._refresh_group_buttons()

        added_names = ", ".join(
            installed_game.display_name
            for installed_game in added_games
        )
        message = f"Added: {added_names}"

        if discovery_errors:
            message += (
                "\n\nSome save folders could not be scanned:\n"
                + "\n".join(discovery_errors)
            )

        if show_messages:
            QMessageBox.information(
                self,
                "Steam Games Detected",
                message,
            )
        return added_games

    def join_hosted_project(self, project: Project) -> None:
        lease = self.project_lock_statuses.get(project.uuid)

        if lease is None or lease.expired:
            QMessageBox.information(
                self,
                "Game No Longer Hosted",
                "The project is no longer marked as hosted by another group member.",
            )
            self._refresh_project_lock_statuses()
            return

        if lease.owner_device_id == self.settings.coordination_device_id:
            QMessageBox.information(
                self,
                "Already Hosting",
                "This computer owns the project lock and is already the host.",
            )
            return

        installed_game = self._get_installed_game_for_project(project)
        supported_game = GameRegistry.get_by_game_id(installed_game.game_id)

        if supported_game is None:
            QMessageBox.warning(
                self,
                "Game Not Supported",
                "Save Shift cannot identify which Steam game to launch.",
            )
            return

        try:
            was_already_running = supported_game.is_running()

            if not was_already_running:
                supported_game.join_hosted_session()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Join Failed",
                f"Save Shift could not launch {supported_game.display_name}.\n\n"
                f"{error}\n\nYou can launch it manually from Steam.",
            )
            return

        if was_already_running:
            launch_message = f"{supported_game.display_name} is already running."
        else:
            launch_message = f"{supported_game.display_name} is launching through Steam."

        QMessageBox.information(
            self,
            "Join Hosted Game",
            f"{launch_message}\n\n"
            f"{lease.owner_display_name} is hosting this project. Join their "
            "session from the game's lobby or accept their Steam invitation.\n\n"
            "Save Shift will not import or modify the host's protected save on "
            "this computer.",
        )

    def receive_or_import_project(self, project: Project) -> None:
        if not self.settings.coordination_enabled:
            self.import_package()
            return

        self._begin_group_receive(project.uuid, project.name, project)

    def _begin_group_receive(
        self,
        project_uuid: str,
        project_name: str,
        project: Project | None = None,
    ) -> None:
        if self.package_handoff_controller.running:
            QMessageBox.information(
                self,
                "Package Transfer In Progress",
                "Wait for the current package transfer to finish.",
            )
            return

        try:
            provider = self._require_coordination_manager().provider
        except CoordinationError as error:
            self._show_coordination_error(error)
            return

        self._pending_receive_project = project
        self._pending_receive_project_name = project_name
        self._show_package_handoff_progress(
            "Receiving Package",
            f"Downloading the latest version of {project_name} from Steam…",
        )

        if not self.package_handoff_controller.download_latest(
            project_uuid,
            provider,
        ):
            self._close_package_handoff_progress()
            self._pending_receive_project = None
            self._pending_receive_project_name = ""

    def show_shared_projects(self) -> None:
        if not self.settings.coordination_enabled:
            QMessageBox.information(
                self,
                "Group Not Connected",
                "Choose Join Group or Create Group on the main screen first.",
            )
            return

        if self.package_handoff_controller.running:
            QMessageBox.information(
                self,
                "Package Transfer In Progress",
                "Wait for the current package transfer to finish.",
            )
            return

        try:
            provider = self._require_coordination_manager().provider
        except CoordinationError as error:
            self._show_coordination_error(error)
            return

        self._listing_shared_projects = True
        self._show_package_handoff_progress(
            "Shared Projects",
            "Checking your group for shared projects…",
        )
        if not self.package_handoff_controller.list_latest_packages(provider):
            self._listing_shared_projects = False
            self._close_package_handoff_progress()

    def _shared_projects_loaded(self, result: object) -> None:
        self._listing_shared_projects = False
        self._close_package_handoff_progress()
        packages = (
            [
                package
                for package in result
                if isinstance(package, CatalogPackage)
                and ProjectRepository.get_by_uuid(
                    package.artifact.project_uuid
                ) is None
            ]
            if isinstance(result, list)
            else []
        )

        if not packages:
            QMessageBox.information(
                self,
                "No New Shared Projects",
                "No group project is waiting to be added on this computer.",
            )
            return

        dialog = SharedProjectsDialog(packages, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dialog.selected_package
        if selected is None:
            return

        project_name = (
            selected.metadata.project_name
            if selected.metadata is not None
            else "Shared project"
        )
        self._begin_group_receive(
            selected.artifact.project_uuid,
            project_name,
        )

    def handoff_or_export_project(self, project: Project) -> None:
        if not self.settings.coordination_enabled:
            self.export_project(project)
            return

        self.handoff_project(project)

    def handoff_project(self, project: Project) -> None:
        if self.package_handoff_controller.running:
            QMessageBox.information(
                self,
                "Package Transfer In Progress",
                "Wait for the current package transfer to finish.",
            )
            return

        installed_game = self._get_installed_game_for_project(project)
        player_name = self._get_player_display_name()

        if player_name is None:
            return

        journal_title = None
        journal_body = None
        add_journal = QMessageBox.question(
            self,
            "Add to World Journal?",
            (
                "Would you like to record what happened during this session "
                "before handing the world off?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if add_journal == QMessageBox.StandardButton.Yes:
            journal_dialog = JournalEntryDialog(project.name, self)

            if journal_dialog.exec() != QDialog.DialogCode.Accepted:
                return

            journal_title = journal_dialog.entry_title
            journal_body = journal_dialog.entry_body

        try:
            manager = self._require_coordination_manager()

            if not manager.has_active_lease(project.uuid):
                self._acquire_hosting_lease(project.uuid, player_name)

            lease = manager.active_leases[project.uuid]
            version = HostingService.host_project(
                project_id=project.id,
                game_id=installed_game.game_id,
                hosted_by=player_name,
                notes="Handed off to the Save Shift group through Steam",
                journal_title=journal_title,
                journal_body=journal_body,
                source_device_name=(
                    self.settings.coordination_device_name or None
                ),
            )

            if not version.package_path:
                raise RuntimeError(
                    "Save Shift created the version without a package path."
                )

            package_path = Path(version.package_path)

            if not package_path.is_file():
                raise FileNotFoundError(
                    f"The generated package could not be found: {package_path}"
                )
        except CoordinationError as error:
            self._show_coordination_error(error)
            return
        except Exception as error:
            QMessageBox.critical(
                self,
                "Hand Off Failed",
                f"Save Shift could not prepare the handoff.\n\n{error}",
            )
            return

        self._pending_handoff_project = project
        self._pending_handoff_version = version
        self._show_package_handoff_progress(
            "Handing Off Project",
            f"Encrypting and uploading {project.name} through Steam…",
        )

        if not self.package_handoff_controller.publish(
            package_path,
            lease,
            manager.provider,
        ):
            self._close_package_handoff_progress()
            self._pending_handoff_project = None
            self._pending_handoff_version = None

    def restore_version(
            self,
            project: Project,
            version: ProjectVersion,
    ) -> ProjectVersion | None:
        player_name = self._get_player_display_name()

        if player_name is None:
            return None

        try:
            with self._temporary_coordination_lease(
                project.uuid,
                player_name,
            ):
                restored_version = RestoreService.restore(
                    project_version=version,
                    restored_by=player_name,
                )
        except CoordinationError as error:
            self._show_coordination_error(error)
            return None
        except FileNotFoundError as error:
            QMessageBox.critical(
                self,
                "Restore Source Missing",
                str(error),
            )
            return None
        except Exception as error:
            QMessageBox.critical(
                self,
                "Restore Failed",
                (
                    f"Save Shift could not restore "
                    f"Version {version.version_number}.\n\n"
                    f"{error}"
                ),
            )
            return None

        QMessageBox.information(
            self,
            "Version Restored",
            (
                f"{project.name} was restored successfully.\n\n"
                f"Restored from Version: {version.version_number}\n"
                f"New history version: "
                f"{restored_version.version_number}"
            ),
        )

        self.load_projects()

        return restored_version

    def _create_project_card(
        self,
        project: Project,
        installed_game: InstalledGame,
    ) -> ProjectCard:
        latest_version = ProjectVersionService.get_latest_version(project.id)
        latest_journal = SessionJournalService.get_latest_entry(project.id)

        card = ProjectCard(
            project=project,
            installed_game=installed_game,
            latest_version=latest_version,
            on_host=self.host_project,
            on_import=(
                lambda selected_project=project:
                self.receive_or_import_project(selected_project)
            ),
            on_export=self.handoff_or_export_project,
            on_history=self.show_history,
            on_join=self.join_hosted_project,
            latest_journal=latest_journal,
            on_journal=self.show_journal,
        )
        self._apply_project_lock_status(project.uuid, card)

        if self.settings.coordination_enabled:
            card.import_button.setText("Receive")
            card.export_button.setText("Hand Off")

        return card

    def _group_handoff_published(self, _package: object) -> None:
        project = self._pending_handoff_project
        version = self._pending_handoff_version
        self._pending_handoff_project = None
        self._pending_handoff_version = None
        self._close_package_handoff_progress()

        if project is None or version is None:
            return

        release_error = self._release_coordination_lease(
            project.uuid,
            report_error=False,
        )
        QMessageBox.information(
            self,
            "Project Handed Off",
            (
                f"{project.name} was encrypted and shared with the group.\n\n"
                f"Version: {version.version_number}"
                + (
                    "\n\nWarning: Save Shift could not release the project "
                    f"lock. It will expire automatically.\n\n{release_error}"
                    if release_error is not None
                    else ""
                )
            ),
        )
        self.load_installed_games()
        self.load_projects()

    def _group_package_downloaded(self, result: object) -> None:
        project_name = self._pending_receive_project_name
        self._pending_receive_project = None
        self._pending_receive_project_name = ""
        self._close_package_handoff_progress()

        if result is None:
            QMessageBox.information(
                self,
                "No Shared Version",
                f"No package has been shared for {project_name} yet.",
            )
            return

        _catalog_package, package_path = result
        package_path = Path(package_path)

        try:
            analysis = ImportService.analyze_import(
                package_path,
                group_authoritative=True,
            )
        except Exception as error:
            package_path.unlink(missing_ok=True)
            QMessageBox.warning(self, "Import Not Allowed", str(error))
            return

        conflict_dialog = ImportConflictDialog(analysis, self)

        if conflict_dialog.exec() != QDialog.DialogCode.Accepted:
            package_path.unlink(missing_ok=True)
            return

        player_name = self._get_player_display_name()

        if player_name is None:
            package_path.unlink(missing_ok=True)
            return

        try:
            with self._temporary_coordination_lease(
                analysis.package_info.project_uuid,
                player_name,
            ):
                version = ImportService.import_package(
                    package_path=package_path,
                    imported_by=player_name,
                    allow_replace=analysis.requires_replace_confirmation,
                    allow_group_reconciliation=True,
                )
        except CoordinationError as error:
            package_path.unlink(missing_ok=True)
            self._show_coordination_error(error)
            return
        except Exception as error:
            package_path.unlink(missing_ok=True)
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Save Shift could not import the shared package.\n\n{error}",
            )
            return

        QMessageBox.information(
            self,
            "Shared Package Received",
            (
                f"{analysis.package_info.project_name} was received successfully.\n\n"
                f"Version: {version.version_number}\n"
                f"Backup created:\n{version.backup_path}"
            ),
        )
        self.load_installed_games()
        self.load_projects()

    def _group_handoff_failed(self, message: str) -> None:
        if self._listing_shared_projects:
            operation = "Shared Projects"
        else:
            operation = (
                "Hand Off"
                if self._pending_handoff_project is not None
                else "Receive"
            )
        self._listing_shared_projects = False
        self._pending_handoff_project = None
        self._pending_handoff_version = None
        self._pending_receive_project = None
        self._pending_receive_project_name = ""
        self._close_package_handoff_progress()
        QMessageBox.critical(
            self,
            f"{operation} Failed",
            (
                f"Save Shift could not complete the group package transfer.\n\n"
                f"{message}"
            ),
        )

    @staticmethod
    def _open_workshop_agreement(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _show_package_handoff_progress(
        self,
        title: str,
        message: str,
    ) -> None:
        self._close_package_handoff_progress()
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle(title)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self._package_handoff_progress = progress

    def _close_package_handoff_progress(self) -> None:
        if self._package_handoff_progress is not None:
            self._package_handoff_progress.close()
            self._package_handoff_progress.deleteLater()
            self._package_handoff_progress = None

    def _clear_installed_game_cards(self) -> None:
        while self.installed_game_layout.count():
            item = self.installed_game_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _clear_project_cards(self) -> None:
        self.project_cards.clear()

        while self.project_layout.count():
            item = self.project_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _get_selected_installed_game(self) -> InstalledGame | None:
        if self.selected_installed_game_id is None:
            return None

        for installed_game in InstalledGameService.get_installed_games():
            if installed_game.id == self.selected_installed_game_id:
                return installed_game

        return None

    def _get_installed_game_for_project(self, project: Project) -> InstalledGame:
        for installed_game in InstalledGameService.get_installed_games():
            if installed_game.id == project.installed_game_id:
                return installed_game

        raise ValueError(f"Installed game not found for project: {project.name}")

    def _get_player_display_name(self) -> str | None:
        if self.settings.player_display_name:
            return self.settings.player_display_name

        display_name, ok = QInputDialog.getText(
            self,
            "Your Name",
            (
                "What name should Save Shift use for project history and "
                "locks? You can change it later in Settings."
            ),
        )
        display_name = display_name.strip()

        if not ok or not display_name:
            return None

        candidate = replace(
            self.settings,
            player_display_name=display_name,
        )

        try:
            SettingsService.save(candidate)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Name Not Saved",
                f"Save Shift could not save your display name.\n\n{error}",
            )
            return None

        self.settings = candidate
        return display_name

    def _refresh_project_lock_statuses(self) -> None:
        if not self.project_cards:
            return

        if not self.settings.coordination_enabled:
            for project_uuid, card in self.project_cards.items():
                self._apply_project_lock_status(project_uuid, card)
            return

        if self.coordination_manager is None:
            for card in self.project_cards.values():
                card.show_lock_unavailable()
            return

        for project_uuid, card in self.project_cards.items():
            if (
                project_uuid not in self.project_lock_statuses
                and not self.coordination_manager.has_active_lease(
                    project_uuid
                )
            ):
                card.show_lock_checking()

        self.lock_status_controller.refresh(
            self.coordination_manager.provider,
            list(self.project_cards),
        )

    def _lock_statuses_loaded(
        self,
        statuses: dict[str, LockLease | None],
    ) -> None:
        self.project_lock_statuses.update(statuses)

        for project_uuid, card in self.project_cards.items():
            self._apply_project_lock_status(project_uuid, card)

    def _lock_statuses_failed(self, message: str) -> None:
        logger.warning("Could not refresh project lock status: %s", message)

        for project_uuid, card in self.project_cards.items():
            if (
                self.coordination_manager is not None
                and self.coordination_manager.has_active_lease(project_uuid)
            ):
                self._apply_project_lock_status(project_uuid, card)
            else:
                card.show_lock_unavailable()

    def _apply_project_lock_status(
        self,
        project_uuid: str,
        card: ProjectCard,
    ) -> None:
        if not self.settings.coordination_enabled:
            card.show_coordination_disabled()
            return

        if self.coordination_manager is None:
            card.show_lock_unavailable()
            return

        lease = self.coordination_manager.active_leases.get(project_uuid)

        if lease is None and project_uuid in self.project_lock_statuses:
            lease = self.project_lock_statuses[project_uuid]

        if lease is not None:
            card.show_lock(
                lease,
                local_device_id=self.settings.coordination_device_id,
            )
        elif project_uuid in self.project_lock_statuses:
            card.show_lock_available()
        else:
            card.show_lock_checking()

    def _set_project_lock_status(self, lease: LockLease) -> None:
        self.project_lock_statuses[lease.project_uuid] = lease
        card = self.project_cards.get(lease.project_uuid)

        if card is not None:
            self._apply_project_lock_status(lease.project_uuid, card)

    @staticmethod
    def _create_coordination_manager(
        settings: AppSettings,
    ) -> CoordinationManager | None:
        if (
            not settings.coordination_enabled
            or not settings.coordination_server_url
            or not settings.coordination_device_id
            or not settings.coordination_device_token
        ):
            return None

        try:
            provider = HttpCoordinationProvider(
                base_url=settings.coordination_server_url,
                device_token=settings.coordination_device_token,
            )
        except CoordinationConfigurationError as error:
            logger.warning("Coordination is not configured correctly: %s", error)
            return None

        return CoordinationManager(provider)

    def _require_coordination_manager(self) -> CoordinationManager:
        if self.coordination_manager is None:
            raise CoordinationConfigurationError(
                "Project coordination is enabled, but this computer is not "
                "paired. Open Settings and pair it with the provider."
            )

        return self.coordination_manager

    def _acquire_hosting_lease(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> None:
        if not self.settings.coordination_enabled:
            return

        lease = self._require_coordination_manager().acquire_hosting_lease(
            project_uuid,
            owner_display_name,
        )
        logger.info(
            "Acquired project lease for %s as %s.",
            project_uuid,
            owner_display_name,
        )
        self._set_project_lock_status(lease)

    @contextmanager
    def _temporary_coordination_lease(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> Generator[None, None, None]:
        if not self.settings.coordination_enabled:
            yield
            return

        manager = self._require_coordination_manager()

        try:
            with manager.temporary_lease(
                project_uuid,
                owner_display_name,
            ) as lease:
                self._set_project_lock_status(lease)
                yield
        finally:
            active_lease = manager.active_leases.get(project_uuid)

            if active_lease is not None:
                self._set_project_lock_status(active_lease)
            else:
                self.project_lock_statuses[project_uuid] = None
                card = self.project_cards.get(project_uuid)

                if card is not None:
                    self._apply_project_lock_status(project_uuid, card)

    def _release_coordination_lease(
        self,
        project_uuid: str,
        *,
        report_error: bool,
    ) -> Exception | None:
        if self.coordination_manager is None:
            return None

        try:
            self.coordination_manager.release_lease(project_uuid)
        except Exception as error:
            logger.warning(
                "Could not release coordination lease for %s: %s",
                project_uuid,
                error,
            )

            if report_error:
                QMessageBox.warning(
                    self,
                    "Project Lock Not Released",
                    (
                        "Save Shift could not release the project lock. "
                        "It will expire automatically.\n\n"
                        f"{error}"
                    ),
                )

            return error

        self.project_lock_statuses[project_uuid] = None
        card = self.project_cards.get(project_uuid)

        if card is not None:
            self._apply_project_lock_status(project_uuid, card)

        logger.info("Released project lease for %s.", project_uuid)

        return None

    def _renew_coordination_leases(self) -> None:
        if self.coordination_manager is None:
            return

        for lease, error in self.coordination_manager.renew_active_leases():
            if isinstance(error, (LockConflictError, LockOwnershipError)):
                self.coordination_manager.forget_lease(lease.project_uuid)
                self.project_lock_statuses.pop(lease.project_uuid, None)
                QMessageBox.critical(
                    self,
                    "Project Lock Lost",
                    (
                        "This computer no longer owns a project lock. Stop "
                        "the game now to avoid conflicting save changes.\n\n"
                        f"{error}"
                    ),
                )
                continue

            logger.warning(
                "Could not renew coordination lease for %s: %s",
                lease.project_uuid,
                error,
            )
            self.statusBar().showMessage(
                "Could not renew a project lock; Save Shift will retry.",
                15_000,
            )

        for lease in self.coordination_manager.active_leases.values():
            self._set_project_lock_status(lease)

        self._refresh_project_lock_statuses()

    def _show_coordination_error(self, error: CoordinationError) -> None:
        if isinstance(error, LockConflictError):
            details = "Another computer currently owns this project lock."

            if error.lock is not None:
                self._set_project_lock_status(error.lock)
                expires_at = error.lock.expires_at_utc.strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
                details = (
                    f"{error.lock.owner_display_name} currently owns this "
                    "project lock.\n\n"
                    f"The lock expires at {expires_at} unless it is renewed."
                )

            QMessageBox.warning(self, "Project In Use", details)
            return

        if isinstance(error, CoordinationUnavailableError):
            QMessageBox.warning(
                self,
                "Coordination Unavailable",
                (
                    "Save Shift could not verify that this project is free. "
                    "No save files were changed. Check your connection and "
                    "try again.\n\n"
                    f"{error}"
                ),
            )
            return

        QMessageBox.warning(self, "Project Coordination", str(error))

    def closeEvent(self, event: QCloseEvent) -> None:
        manager = self.coordination_manager

        if manager is not None and manager.active_leases:
            response = QMessageBox.question(
                self,
                "Release Project Locks?",
                (
                    "Save Shift is holding one or more project locks. Close "
                    "the game before exiting.\n\n"
                    "Exit and release the locks now?"
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if response != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            failures = manager.release_all()

            if failures:
                logger.warning(
                    "Could not release %s coordination lease(s) on exit.",
                    len(failures),
                )

        self.coordination_renewal_timer.stop()
        self.lock_status_timer.stop()
        event.accept()
        super().closeEvent(event)
