from contextlib import contextmanager
from collections.abc import Generator
from dataclasses import replace
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
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
from app.core.logging import logger
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
from app.games.registry import GameRegistry
from app.services.export_service import ExportService
from app.services.restore_service import RestoreService
from app.services.hosting_service import HostingService
from app.services.import_service import ImportService
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.services.project_version_service import ProjectVersionService
from app.ui import styles, theme
from app.ui.widgets.installed_game_card import InstalledGameCard
from app.ui.widgets.project_card import ProjectCard
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.dialogs.settings_dialog import SettingsDialog
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
        self.settings = SettingsService.load()
        self.coordination_manager = self._create_coordination_manager(
            self.settings
        )
        self.coordination_renewal_timer = QTimer(self)
        self.coordination_renewal_timer.setInterval(5 * 60 * 1000)
        self.coordination_renewal_timer.timeout.connect(
            self._renew_coordination_leases
        )

        if self.coordination_manager is not None:
            self.coordination_renewal_timer.start()

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

        self.remove_button = QPushButton("Remove Game")
        self.remove_button.clicked.connect(self.remove_selected_game)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.show_settings)


        for button in (
            self.add_button,
            self.remove_button,
            self.settings_button,
        ):
            button.setStyleSheet(styles.secondary_button_style())

        left_panel = QVBoxLayout()
        left_panel.addWidget(self.installed_game_heading)
        left_panel.addWidget(self.installed_game_scroll, 1)
        left_panel.addSpacing(theme.SPACING)
        left_panel.addWidget(self.add_button)
        left_panel.addWidget(self.remove_button)
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

        if startup_package_path is not None:
            QTimer.singleShot(
                0,
                lambda: self.import_package(startup_package_path),
            )
        else:
            QTimer.singleShot(0, self._start_automatic_update_check)

    def show_settings(self) -> None:
        dialog = SettingsDialog(
            settings=self.settings,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
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

        if self.coordination_manager is not None:
            self.coordination_renewal_timer.start()
        else:
            self.coordination_renewal_timer.stop()

        if dialog.check_requested:
            self.check_for_updates(manual=True)

    def check_for_updates(self, *, manual: bool = True) -> None:
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
            self.project_layout.addWidget(card)

        self.project_layout.addStretch()

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
                "Save Folder Found",
                (
                    f"Save Shift found the default save folder for "
                    f"{supported_game.display_name}:\n\n"
                    f"{detected_save_path}\n\n"
                    "Use this folder?"
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

        hosted_by, ok = QInputDialog.getText(
            self,
            "Host Project",
            "Who is hosting this version?",
        )

        if not ok or not hosted_by.strip():
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
                    "Export the project when you are ready to hand it off."
                ),
            )
            return

        try:
            self._acquire_hosting_lease(project.uuid, hosted_by.strip())
        except CoordinationError as error:
            self._show_coordination_error(error)
            return

        try:
            version = HostingService.host_project(
                project_id=project.id,
                game_id=installed_game.game_id,
                hosted_by=hosted_by.strip(),
            )
        except Exception as error:
            self._release_coordination_lease(project.uuid, report_error=False)
            QMessageBox.critical(
                self,
                "Hosting Failed",
                f"Save Shift could not host this project.\n\n{error}",
            )
            return

        self.load_installed_games()
        self.load_projects()

        supported_game = GameRegistry.get_by_game_id(
            installed_game.game_id
        )

        if supported_game is None:
            QMessageBox.information(
                self,
                "Project Hosted",
                (
                    "Hosted version created successfully.\n\n"
                    f"Version: {version.version_number}\n"
                    f"Package:\n{version.package_path}\n\n"
                    "The game could not be identified, so it was not "
                    "launched automatically."
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
                    "Hosted version created successfully.\n\n"
                    f"Version: {version.version_number}\n"
                    f"Package:\n{version.package_path}\n\n"
                    "However, Save Shift could not launch "
                    f"{supported_game.display_name} automatically.\n\n"
                    f"{error}\n\n"
                    "You can launch it manually from Steam."
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
                "Hosted version created successfully.\n\n"
                f"Version: {version.version_number}\n"
                f"Package:\n{version.package_path}\n\n"
                f"{launch_message}"
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
            package_info = ImportService.validate_import_package(package_path)
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

        imported_by, ok = QInputDialog.getText(
            self,
            "Import Package",
            "Who is importing this package?",
        )

        if not ok or not imported_by.strip():
            return

        try:
            with self._temporary_coordination_lease(
                package_info.project_uuid,
                imported_by.strip(),
            ):
                version = ImportService.import_package(
                    package_path=package_path,
                    imported_by=imported_by.strip(),
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

        exported_by, ok = QInputDialog.getText(
            self,
            "Export Package",
            "Who is exporting this project?",
        )

        if not ok or not exported_by.strip():
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

        lease_acquired_here = False

        try:
            if self.settings.coordination_enabled:
                manager = self._require_coordination_manager()

                if not manager.has_active_lease(project.uuid):
                    manager.acquire_hosting_lease(
                        project.uuid,
                        exported_by.strip(),
                    )
                    lease_acquired_here = True

            version = ExportService.export_project(
                project=project,
                game_id=installed_game.game_id,
                exported_by=exported_by.strip(),
                destination_path=destination,
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
            parent=self,
        )
        dialog.exec()

    def restore_version(
            self,
            project: Project,
            version: ProjectVersion,
    ) -> ProjectVersion | None:
        restored_by, ok = QInputDialog.getText(
            self,
            "Restore Version",
            "Who is restoring this project?",
        )

        if not ok or not restored_by.strip():
            return None

        try:
            with self._temporary_coordination_lease(
                project.uuid,
                restored_by.strip(),
            ):
                restored_version = RestoreService.restore(
                    project_version=version,
                    restored_by=restored_by.strip(),
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

        return ProjectCard(
            project=project,
            installed_game=installed_game,
            latest_version=latest_version,
            on_host=self.host_project,
            on_import=self.import_package,
            on_export=self.export_project,
            on_history=self.show_history,
        )

    def _clear_installed_game_cards(self) -> None:
        while self.installed_game_layout.count():
            item = self.installed_game_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _clear_project_cards(self) -> None:
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

        self._require_coordination_manager().acquire_hosting_lease(
            project_uuid,
            owner_display_name,
        )

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

        with manager.temporary_lease(project_uuid, owner_display_name):
            yield

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

        return None

    def _renew_coordination_leases(self) -> None:
        if self.coordination_manager is None:
            return

        for lease, error in self.coordination_manager.renew_active_leases():
            if isinstance(error, (LockConflictError, LockOwnershipError)):
                self.coordination_manager.forget_lease(lease.project_uuid)
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

    def _show_coordination_error(self, error: CoordinationError) -> None:
        if isinstance(error, LockConflictError):
            details = "Another computer currently owns this project lock."

            if error.lock is not None:
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
        event.accept()
        super().closeEvent(event)
