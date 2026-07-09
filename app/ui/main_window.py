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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.games.registry import GameRegistry
from app.services.hosting_service import HostingService
from app.services.import_service import ImportService
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.services.project_version_service import ProjectVersionService
from app.ui.widgets.project_card import ProjectCard
from app.ui.widgets.installed_game_card import InstalledGameCard
from app.ui import theme


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Save Shift")
        self.setMinimumSize(850, 600)

        self.installed_game_ids_by_row: dict[int, int] = {}

        self.title = QLabel("Save Shift")
        self.title.setStyleSheet("font-size: 28px; font-weight: bold;")

        self.subtitle = QLabel("Seamlessly hand off self-hosted co-op game worlds between friends.")
        self.subtitle.setStyleSheet("font-size: 14px; color: gray;")

        self.installed_game_container = QWidget()

        self.installed_game_layout = QVBoxLayout()
        self.installed_game_layout.setSpacing(theme.SPACING)

        self.installed_game_container.setLayout(
            self.installed_game_layout
        )

        self.project_scroll = QScrollArea()
        self.project_scroll.setWidgetResizable(True)

        self.project_container = QWidget()
        self.project_layout = QVBoxLayout()
        self.project_layout.setSpacing(12)
        self.project_container.setLayout(self.project_layout)

        self.project_scroll.setWidget(self.project_container)

        self.add_button = QPushButton("Add Installed Game")
        self.add_button.clicked.connect(self.add_installed_game)

        self.remove_button = QPushButton("Remove Selected Game")
        self.remove_button.clicked.connect(self.remove_selected_game)

        self.discover_button = QPushButton("Discover Projects")
        self.discover_button.clicked.connect(self.discover_projects_for_selected_game)

        game_button_row = QHBoxLayout()
        game_button_row.addWidget(self.add_button)
        game_button_row.addWidget(self.remove_button)
        game_button_row.addWidget(self.discover_button)

        layout = QVBoxLayout()
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(QLabel("Installed Games"))
        layout.addWidget(self.installed_game_container)
        layout.addLayout(game_button_row)
        layout.addWidget(QLabel("Projects"))
        layout.addWidget(self.project_scroll)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.load_installed_games()
        self.load_projects()

    def load_installed_games(self) -> None:
        self._clear_installed_game_cards()

        installed_games = InstalledGameService.get_installed_games()

        for installed_game in installed_games:
            projects = ProjectService.get_projects_for_installed_game(
                installed_game.id
            )

            card = InstalledGameCard(
                installed_game,
                len(projects),
            )

            self.installed_game_layout.addWidget(card)

        self.installed_game_layout.addStretch()

    def load_projects(self) -> None:
        self._clear_project_cards()

        installed_games = InstalledGameService.get_installed_games()
        project_count = 0

        for installed_game in installed_games:
            projects = ProjectService.get_projects_for_installed_game(installed_game.id)

            for project in projects:
                card = self._create_project_card(
                    project=project,
                    installed_game=installed_game,
                )

                self.project_layout.addWidget(card)
                project_count += 1

        if project_count == 0:
            empty_label = QLabel("No projects discovered yet. Select a game and click Discover Projects.")
            empty_label.setStyleSheet("color: gray;")
            self.project_layout.addWidget(empty_label)

        self.project_layout.addStretch()

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

    def host_project(self, project: Project) -> None:
        installed_game = self._get_installed_game_for_project(project)

        hosted_by, ok = QInputDialog.getText(
            self,
            "Host Project",
            "Who is hosting this version?",
        )

        if not ok or not hosted_by.strip():
            return

        try:
            version = HostingService.host_project(
                project_id=project.id,
                game_id=installed_game.game_id,
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

        self.load_installed_games()
        self.load_projects()

    def import_package(self, project: Project) -> None:
        package_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Save Shift Package",
            "",
            "Save Shift Packages (*.sspkg)",
        )

        if not package_path:
            return

        try:
            ImportService.validate_import_package(Path(package_path))
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Import Not Allowed",
                str(error),
            )
            return
        except FileNotFoundError as error:
            QMessageBox.critical(
                self,
                "Package Not Found",
                str(error),
            )
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

        self.load_installed_games()
        self.load_projects()

    def show_history(self, project: Project) -> None:
        QMessageBox.information(
            self,
            "History",
            f"History view for {project.name} is coming soon.",
        )

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

    def _get_installed_game_for_project(self, project: Project) -> InstalledGame:
        installed_games = InstalledGameService.get_installed_games()

        for installed_game in installed_games:
            if installed_game.id == project.installed_game_id:
                return installed_game

        raise ValueError(f"Installed game not found for project: {project.name}")