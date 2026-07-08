from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.games.registry import GameRegistry
from app.services.hosting_service import HostingService
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.services.project_version_service import ProjectVersionService
from app.services.import_service import ImportService


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Save Shift")
        self.setMinimumSize(850, 600)

        self.installed_game_ids_by_row: dict[int, int] = {}
        self.project_context_by_row: dict[int, tuple[int, str]] = {}

        self.title = QLabel("Save Shift")
        self.title.setStyleSheet("font-size: 28px; font-weight: bold;")

        self.subtitle = QLabel("Seamlessly hand off self-hosted co-op game worlds between friends.")
        self.subtitle.setStyleSheet("font-size: 14px; color: gray;")

        self.installed_game_list = QListWidget()
        self.project_list = QListWidget()

        self.add_button = QPushButton("Add Installed Game")
        self.add_button.clicked.connect(self.add_installed_game)

        self.remove_button = QPushButton("Remove Selected Game")
        self.remove_button.clicked.connect(self.remove_selected_game)

        self.discover_button = QPushButton("Discover Projects")
        self.discover_button.clicked.connect(self.discover_projects_for_selected_game)

        self.host_button = QPushButton("Host Selected Project")
        self.host_button.clicked.connect(self.host_selected_project)

        self.import_button = QPushButton("Import Package")
        self.import_button.clicked.connect(self.import_package)

        game_button_row = QHBoxLayout()
        game_button_row.addWidget(self.add_button)
        game_button_row.addWidget(self.remove_button)
        game_button_row.addWidget(self.discover_button)

        project_button_row = QHBoxLayout()
        project_button_row.addWidget(self.host_button)
        project_button_row.addWidget(self.import_button)

        layout = QVBoxLayout()
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(QLabel("Installed Games"))
        layout.addWidget(self.installed_game_list)
        layout.addLayout(game_button_row)
        layout.addWidget(QLabel("Projects"))
        layout.addWidget(self.project_list)
        layout.addLayout(project_button_row)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.load_installed_games()
        self.load_projects()

    def load_installed_games(self) -> None:
        self.installed_game_list.clear()
        self.installed_game_ids_by_row.clear()

        installed_games = InstalledGameService.get_installed_games()

        if not installed_games:
            item = QListWidgetItem("No installed games configured yet. Click Add Installed Game to begin.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.installed_game_list.addItem(item)
            return

        for row, installed_game in enumerate(installed_games):
            item_text = (
                f"{installed_game.display_name}\n"
                f"Save folder: {installed_game.save_path}"
            )

            item = QListWidgetItem(item_text)
            self.installed_game_list.addItem(item)
            self.installed_game_ids_by_row[row] = installed_game.id

    def load_projects(self) -> None:
        self.project_list.clear()
        self.project_context_by_row.clear()

        installed_games = InstalledGameService.get_installed_games()

        row = 0

        for installed_game in installed_games:
            projects = ProjectService.get_projects_for_installed_game(installed_game.id)

            for project in projects:
                latest_version = ProjectVersionService.get_latest_version(project.id)

                version_text = (
                    f"Version {latest_version.version_number}"
                    if latest_version is not None
                    else "No versions yet"
                )

                hosted_by_text = (
                    f"Last updated by: {latest_version.created_by}"
                    if latest_version is not None
                    else "Last updated by: Nobody yet"
                )

                item_text = (
                    f"{project.name}\n"
                    f"Game: {installed_game.display_name}\n"
                    f"{version_text}\n"
                    f"{hosted_by_text}\n"
                    f"Save folder: {project.local_path}"
                )

                item = QListWidgetItem(item_text)
                self.project_list.addItem(item)
                self.project_context_by_row[row] = (project.id, installed_game.game_id)
                row += 1

        if row == 0:
            item = QListWidgetItem("No projects discovered yet. Select a game and click Discover Projects.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.project_list.addItem(item)

    def add_installed_game(self) -> None:
        supported_games = GameRegistry.all()
        game_names = [game.display_name for game in supported_games]

        selected_game_name, ok = QInputDialog.getItem(
            self,
            "Add Installed Game",
            "Choose a supported game:",
            game_names,
            0,
            False,
        )

        if not ok or not selected_game_name:
            return

        supported_game = GameRegistry.get_by_display_name(selected_game_name)

        if supported_game is None:
            QMessageBox.warning(self, "Unsupported Game", "That game is not supported.")
            return

        save_path = QFileDialog.getExistingDirectory(
            self,
            "Select the game's existing save folder",
        )

        if not save_path:
            return

        InstalledGameService.add_installed_game(
            game_id=supported_game.game_id,
            display_name=supported_game.display_name,
            save_path=save_path,
        )

        self.load_installed_games()
        self.load_projects()

    def remove_selected_game(self) -> None:
        row = self.installed_game_list.currentRow()

        if row not in self.installed_game_ids_by_row:
            QMessageBox.information(self, "No Game Selected", "Please select a configured game first.")
            return

        confirm = QMessageBox.question(
            self,
            "Remove Game",
            "Remove this game from Save Shift? This will not delete any save files.",
        )

        if confirm != QMessageBox.Yes:
            return

        InstalledGameService.delete_installed_game(self.installed_game_ids_by_row[row])
        self.load_installed_games()
        self.load_projects()

    def discover_projects_for_selected_game(self) -> None:
        row = self.installed_game_list.currentRow()

        if row not in self.installed_game_ids_by_row:
            QMessageBox.information(self, "No Game Selected", "Please select a configured game first.")
            return

        installed_game_id = self.installed_game_ids_by_row[row]
        projects = ProjectService.discover_projects(installed_game_id)

        if not projects:
            QMessageBox.information(
                self,
                "No Projects Found",
                "No projects were found in that save folder.",
            )
            self.load_projects()
            return

        project_summary = "\n".join(
            f"• {project.name}"
            for project in projects
        )

        QMessageBox.information(
            self,
            "Projects Discovered",
            f"Save Shift found:\n\n{project_summary}",
        )

        self.load_installed_games()
        self.load_projects()

    def host_selected_project(self) -> None:
        row = self.project_list.currentRow()

        if row not in self.project_context_by_row:
            QMessageBox.information(self, "No Project Selected", "Please select a project first.")
            return

        project_id, game_id = self.project_context_by_row[row]

        hosted_by, ok = QInputDialog.getText(
            self,
            "Host Project",
            "Who is hosting this version?",
        )

        if not ok or not hosted_by.strip():
            return

        try:
            version = HostingService.host_project(
                project_id=project_id,
                game_id=game_id,
                hosted_by=hosted_by.strip(),
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Hosting Failed",
                f"Save Shift could not host this project.\n\n{error}",
            )
            return

        QMessageBox.information(
            self,
            "Project Hosted",
            (
                f"Hosted version created successfully.\n\n"
                f"Version: {version.version_number}\n"
                f"Package:\n{version.package_path}"
            ),
        )

        self.load_projects()

    def import_package(self) -> None:
        package_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Save Shift Package",
            "",
            "Save Shift Packages (*.sspkg)",
        )

        if not package_path:
            return

        imported_by, ok = QInputDialog.getText(
            self,
            "Import Package",
            "Who is importing this package?",
        )

        if not ok or not imported_by.strip():
            return

        try:
            version = ImportService.import_package(
                package_path=Path(package_path),
                imported_by=imported_by.strip(),
            )
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

        self.load_projects()