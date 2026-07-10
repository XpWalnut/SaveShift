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
    QVBoxLayout,
)

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_version_repository import ProjectVersionRepository
from app.services.project_version_service import ProjectVersionService
from app.ui import styles, theme


class HistoryDialog(QDialog):
    def __init__(
            self,
            project: Project,
            on_restore: Callable[
                [ProjectVersion],
                ProjectVersion | None,
            ],
            parent=None,
    ) -> None:
        super().__init__(parent)

        self.project = project
        self.on_restore = on_restore
        self.versions_by_row: dict[int, ProjectVersion] = {}

        self.setWindowTitle(f"History — {project.name}")
        self.setMinimumSize(700, 500)

        title = QLabel(f"Version History — {project.name}")
        title.setStyleSheet(
            f"""
            color: {theme.TEXT_PRIMARY};
            font-size: 22px;
            font-weight: bold;
            """
        )

        subtitle = QLabel(
            "Select a version to view its details or restore the project to it."
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

        close_button = QPushButton("Close")
        close_button.setStyleSheet(styles.secondary_button_style())
        close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.restore_button)
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
        layout.addWidget(self.version_list)
        layout.addLayout(button_row)

        self.setLayout(layout)
        self.setStyleSheet(
            f"background-color: {theme.WINDOW_BACKGROUND};"
        )

        self._load_versions()

    def _load_versions(self) -> None:
        self.version_list.clear()
        self.versions_by_row.clear()

        versions = ProjectVersionService.get_versions_for_project(
            self.project.id
        )

        versions = sorted(
            versions,
            key=lambda version: version.version_number,
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
                f"Version {version.version_number}",
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