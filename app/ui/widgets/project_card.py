from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui import theme, styles
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion


class ProjectCard(QFrame):
    def __init__(
            self,
            project: Project,
            installed_game: InstalledGame,
            latest_version: ProjectVersion | None,
            on_host,
            on_import,
            on_history,
            parent=None,
    ) -> None:
        super().__init__(parent)

        self.project = project

        self.setObjectName("ProjectCard")
        self.setStyleSheet(
            styles.card_style("ProjectCard")
            + styles.primary_button_style()
        )

        title = QLabel(f"🌍 {project.name}")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        game_label = QLabel(f"🎮 {installed_game.display_name}")
        game_label.setObjectName("SecondaryText")

        if latest_version is None:
            version_text = "📈 No versions yet"
            updated_by_text = "👤 Nobody yet"
        else:
            version_text = f"📈 Main Timeline • Version {latest_version.version_number}"
            updated_by_text = f"👤 Last updated by {latest_version.created_by}"

        version_label = QLabel(version_text)
        version_label.setObjectName("SecondaryText")

        updated_by_label = QLabel(updated_by_text)
        updated_by_label.setObjectName("SecondaryText")

        self.host_button = QPushButton("Host")
        self.import_button = QPushButton("Import")
        self.history_button = QPushButton("History")

        for button in (
                self.host_button,
                self.import_button,
                self.history_button,
        ):
            button.setMinimumWidth(115)

        button_row = QHBoxLayout()
        button_row.addWidget(self.host_button)
        button_row.addWidget(self.import_button)
        button_row.addWidget(self.history_button)
        button_row.addStretch()

        self.host_button.clicked.connect(
            lambda: on_host(project)
        )

        self.import_button.clicked.connect(
            lambda: on_import(project)
        )

        self.history_button.clicked.connect(
            lambda: on_history(project)
        )

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(game_label)
        layout.addSpacing(8)
        layout.addWidget(version_label)
        layout.addWidget(updated_by_label)
        layout.addSpacing(12)
        layout.addLayout(button_row)

        layout.addStretch(0)
        layout.setContentsMargins(
            theme.SPACING,
            theme.SPACING,
            theme.SPACING,
            theme.SPACING,
        )
        layout.setSpacing(theme.SPACING_SMALL)

        self.setLayout(layout)