from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui import theme, styles
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.models.session_journal_entry import SessionJournalEntry
from app.coordination.models import LockLease


class ProjectCard(QFrame):
    def __init__(
            self,
            project: Project,
            installed_game: InstalledGame,
            latest_version: ProjectVersion | None,
            on_host,
            on_import,
            on_export,
            on_history,
            latest_journal: SessionJournalEntry | None = None,
            on_journal=None,
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

        if latest_journal is None:
            journal_text = "World Journal: No entries yet"
        else:
            journal_text = (
                f'World Journal: “{latest_journal.title}” — '
                f"{latest_journal.created_by}"
            )

        self.journal_preview_label = QLabel(journal_text)
        self.journal_preview_label.setWordWrap(True)
        self.journal_preview_label.setObjectName("SecondaryText")

        self.lock_status_label = QLabel()
        self.lock_status_label.setWordWrap(True)
        self.lock_status_label.setObjectName("SecondaryText")
        self.show_coordination_disabled()

        self.host_button = QPushButton("Host")
        self.import_button = QPushButton("Import")
        self.export_button = QPushButton("Export")
        self.history_button = QPushButton("History")
        self.journal_button = QPushButton("Journal")

        for button in (
                self.host_button,
                self.import_button,
                self.export_button,
                self.history_button,
                self.journal_button,
        ):
            button.setMinimumWidth(105)

        button_row = QHBoxLayout()
        button_row.addWidget(self.host_button)
        button_row.addWidget(self.import_button)
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.history_button)
        button_row.addWidget(self.journal_button)
        button_row.addStretch()

        self.host_button.clicked.connect(
            lambda: on_host(project)
        )

        self.import_button.clicked.connect(
            lambda checked=False: on_import()
        )

        self.export_button.clicked.connect(
            lambda: on_export(project)
        )

        self.history_button.clicked.connect(
            lambda: on_history(project)
        )

        if on_journal is not None:
            self.journal_button.clicked.connect(
                lambda: on_journal(project)
            )
        else:
            self.journal_button.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(game_label)
        layout.addSpacing(8)
        layout.addWidget(version_label)
        layout.addWidget(updated_by_label)
        layout.addWidget(self.journal_preview_label)
        layout.addWidget(self.lock_status_label)
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

    def show_coordination_disabled(self) -> None:
        self.lock_status_label.setText(
            "Project lock: Local protection only — coordination disabled"
        )
        self.lock_status_label.setStyleSheet("")

    def show_lock_checking(self) -> None:
        self.lock_status_label.setText("Project lock: Checking…")
        self.lock_status_label.setStyleSheet("")

    def show_lock_available(self) -> None:
        self.lock_status_label.setText("Project lock: Available")
        self.lock_status_label.setStyleSheet(f"color: {theme.SUCCESS};")

    def show_lock_unavailable(self) -> None:
        self.lock_status_label.setText("Project lock: Status unavailable")
        self.lock_status_label.setStyleSheet(f"color: {theme.WARNING};")

    def show_lock(
        self,
        lease: LockLease,
        *,
        local_device_id: str,
    ) -> None:
        owner_suffix = (
            " (this computer)"
            if lease.owner_device_id == local_device_id
            else ""
        )
        expires_at = lease.expires_at_utc.astimezone().strftime(
            "%b %d, %Y at %I:%M:%S %p %Z"
        )
        self.lock_status_label.setText(
            f"Project lock: Locked by {lease.owner_display_name}"
            f"{owner_suffix} · Expires {expires_at} unless renewed"
        )
        self.lock_status_label.setStyleSheet(f"color: {theme.WARNING};")
