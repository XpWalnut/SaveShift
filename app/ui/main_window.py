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
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService


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

        self.installed_game_list = QListWidget()

        self.add_button = QPushButton("Add Installed Game")
        self.add_button.clicked.connect(self.add_installed_game)

        self.remove_button = QPushButton("Remove Selected Game")
        self.remove_button.clicked.connect(self.remove_selected_game)

        self.discover_button = QPushButton("Discover Projects")
        self.discover_button.clicked.connect(self.discover_projects_for_selected_game)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.remove_button)
        button_row.addWidget(self.discover_button)

        layout = QVBoxLayout()
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.installed_game_list)
        layout.addLayout(button_row)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.load_installed_games()

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
            projects = ProjectService.get_projects_for_installed_game(installed_game.id)

            project_lines = "\n".join(
                f"    • {project.name}"
                for project in projects
            )

            if not project_lines:
                project_lines = "    No projects discovered yet."

            item_text = (
                f"{installed_game.display_name}\n"
                f"Save folder: {installed_game.save_path}\n"
                f"Projects:\n"
                f"{project_lines}"
            )

            item = QListWidgetItem(item_text)
            self.installed_game_list.addItem(item)
            self.installed_game_ids_by_row[row] = installed_game.id

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