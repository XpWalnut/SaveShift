from datetime import UTC
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_version_repository import ProjectVersionRepository
from app.services.project_version_service import ProjectVersionService
from app.services.session_journal_service import SessionJournalService
from app.ui import styles, theme


class HistoryDialog(QDialog):
    def __init__(
            self,
            project: Project,
            on_restore: Callable[
                [ProjectVersion],
                ProjectVersion | None,
            ],
            on_add_journal: Callable[[], object | None] | None = None,
            initial_tab: str = "versions",
            parent=None,
    ) -> None:
        super().__init__(parent)

        self.project = project
        self.on_restore = on_restore
        self.on_add_journal = on_add_journal
        self.versions_by_row: dict[int, ProjectVersion] = {}

        self.setWindowTitle(f"History — {project.name}")
        self.setMinimumSize(700, 500)

        title = QLabel(f"World History — {project.name}")
        title.setStyleSheet(
            f"""
            color: {theme.TEXT_PRIMARY};
            font-size: 22px;
            font-weight: bold;
            """
        )

        subtitle = QLabel(
            "Review save versions and the group's journal of shared adventures."
        )
        subtitle.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY};"
        )

        self.version_list = QListWidget()
        self.version_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {theme.CARD_BACKGROUND};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.CARD_BORDER};
                border-radius: {theme.CARD_RADIUS}px;
                padding: {theme.SPACING_SMALL}px;
            }}

            QListWidget::item {{
                border-bottom: 1px solid {theme.CARD_BORDER};
                padding: 10px;
            }}

            QListWidget::item:selected {{
                background-color: {theme.ACCENT};
                color: {theme.TEXT_PRIMARY};
            }}
            """
        )

        self.restore_button = QPushButton("Restore Selected Version")
        self.restore_button.setStyleSheet(styles.primary_button_style())
        self.restore_button.clicked.connect(self._restore_selected_version)

        version_button_row = QHBoxLayout()
        version_button_row.addStretch()
        version_button_row.addWidget(self.restore_button)

        version_tab = QWidget()
        version_layout = QVBoxLayout()
        version_layout.addWidget(self.version_list)
        version_layout.addLayout(version_button_row)
        version_tab.setLayout(version_layout)

        self.journal_list = QListWidget()
        self.journal_list.setWordWrap(True)
        self.journal_list.setStyleSheet(self.version_list.styleSheet())

        self.add_journal_button = QPushButton("Add Journal Entry")
        self.add_journal_button.setStyleSheet(styles.primary_button_style())
        self.add_journal_button.clicked.connect(self._add_journal_entry)
        self.add_journal_button.setEnabled(on_add_journal is not None)

        journal_button_row = QHBoxLayout()
        journal_button_row.addStretch()
        journal_button_row.addWidget(self.add_journal_button)

        journal_tab = QWidget()
        journal_layout = QVBoxLayout()
        journal_layout.addWidget(self.journal_list)
        journal_layout.addLayout(journal_button_row)
        journal_tab.setLayout(journal_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(version_tab, "Version History")
        self.tabs.addTab(journal_tab, "World Journal")

        if initial_tab == "journal":
            self.tabs.setCurrentWidget(journal_tab)

        close_button = QPushButton("Close")
        close_button.setStyleSheet(styles.secondary_button_style())
        close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
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
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(button_row)

        self.setLayout(layout)
        self.setStyleSheet(
            f"background-color: {theme.WINDOW_BACKGROUND};"
        )

        self._load_versions()
        self._load_journal_entries()

    def _load_versions(self) -> None:
        self.version_list.clear()
        self.versions_by_row.clear()

        versions = ProjectVersionService.get_versions_for_project(
            self.project.id
        )
        current_version = ProjectVersionService.get_latest_version(
            self.project.id
        )

        versions = sorted(
            versions,
            key=lambda version: version.id,
            reverse=True,
        )

        if not versions:
            item = QListWidgetItem("No versions have been recorded yet.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.version_list.addItem(item)
            self.restore_button.setEnabled(False)
            return

        self.restore_button.setEnabled(True)

        for row, version in enumerate(versions):
            created_at = version.created_at_utc

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)

            local_time = created_at.astimezone()

            details = [
                (
                    f"Version {version.version_number} · Current"
                    if current_version is not None
                    and version.id == current_version.id
                    else f"Version {version.version_number}"
                ),
                f"{version.source_type} by {version.created_by}",
                local_time.strftime("%B %d, %Y at %I:%M %p"),
                f"Timeline: {version.lineage_name}",
            ]

            if version.restored_from_version_id is not None:
                restored_from = ProjectVersionRepository.get_by_id(
                    version.restored_from_version_id
                )

                if restored_from is not None:
                    details.append(
                        f"Restored from Version {restored_from.version_number}"
                    )

            if version.notes:
                details.append(f"Notes: {version.notes}")

            item = QListWidgetItem("\n".join(details))
            self.version_list.addItem(item)
            self.versions_by_row[row] = version

        self.version_list.setCurrentRow(0)

    def _restore_selected_version(self) -> None:
        row = self.version_list.currentRow()
        version = self.versions_by_row.get(row)

        if version is None:
            QMessageBox.information(
                self,
                "No Version Selected",
                "Please select a version to restore.",
            )
            return

        confirmation = QMessageBox.warning(
            self,
            "Restore Version",
            (
                f"Restore {self.project.name} to Version "
                f"{version.version_number}?\n\n"
                "The current save files will be overwritten."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if confirmation != QMessageBox.StandardButton.Yes:
            return

        restored_version = self.on_restore(version)

        if restored_version is not None:
            self.accept()

    def _load_journal_entries(self) -> None:
        self.journal_list.clear()
        entries = SessionJournalService.get_entries_for_project(self.project.id)

        if not entries:
            item = QListWidgetItem(
                "No journal entries yet. Record the group's first adventure."
            )
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.journal_list.addItem(item)
            return

        for entry in reversed(entries):
            created_at = entry.created_at_utc

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)

            details = [
                entry.title,
                f"{entry.created_by} · "
                f"{created_at.astimezone().strftime('%B %d, %Y at %I:%M %p')}",
            ]

            if entry.project_version_number is not None:
                details.append(f"Version {entry.project_version_number}")

            details.extend(["", entry.body])
            self.journal_list.addItem(QListWidgetItem("\n".join(details)))

    def _add_journal_entry(self) -> None:
        if self.on_add_journal is None:
            return

        if self.on_add_journal() is not None:
            self._load_journal_entries()
