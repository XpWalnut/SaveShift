from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.services.import_conflict import ImportAnalysis, ImportConflictKind
from app.ui import styles, theme


_STATUS_CONTENT = {
    ImportConflictKind.NEW_PROJECT: (
        "New project",
        "This package will create a new tracked project on this computer.",
        theme.SUCCESS,
    ),
    ImportConflictKind.NEW_PROJECT_REPLACE_EXISTING: (
        "Existing save files found",
        "This package has a new project identity, but its destination already "
        "contains save files. Save Shift will back them up before replacing "
        "the directory.",
        theme.WARNING,
    ),
    ImportConflictKind.ADOPT_EXISTING_PROJECT: (
        "Existing local project found",
        "This save was discovered locally before it joined the shared "
        "project. Save Shift will back it up and adopt the package's shared "
        "identity instead of creating a duplicate project card.",
        theme.WARNING,
    ),
    ImportConflictKind.IDENTITY_COLLISION: (
        "Project identity conflict blocked",
        "A differently identified project already tracks this destination "
        "and has its own version history. Save Shift cannot safely combine "
        "the two timelines automatically.",
        theme.ERROR,
    ),
    ImportConflictKind.FAST_FORWARD: (
        "Verified continuation",
        "The package directly continues the current local version.",
        theme.SUCCESS,
    ),
    ImportConflictKind.REPLACE_UNVERSIONED: (
        "Unversioned local save",
        "The local save has no recorded versions. If save files are present, "
        "Save Shift will back them up before replacing them.",
        theme.WARNING,
    ),
    ImportConflictKind.UNVERIFIED_NEWER: (
        "Ancestry unavailable",
        "The package is newer, but it does not contain enough ancestry "
        "metadata to prove that it continues the local version.",
        theme.WARNING,
    ),
    ImportConflictKind.DIVERGED: (
        "History has diverged",
        "The package does not continue the current local version. Importing "
        "will back up and replace the current save while preserving both "
        "states in history.",
        theme.WARNING,
    ),
    ImportConflictKind.OLDER: (
        "Older package blocked",
        "The package is older than the current project. Use version history "
        "to restore an earlier state safely.",
        theme.ERROR,
    ),
    ImportConflictKind.DUPLICATE: (
        "Already imported",
        "This exact package version is already the current local version.",
        theme.ERROR,
    ),
    ImportConflictKind.VERSION_COLLISION: (
        "Version collision blocked",
        "The package uses the current version number but contains different "
        "data. Save Shift cannot safely place both at the same history point.",
        theme.ERROR,
    ),
}


class ImportConflictDialog(QDialog):
    def __init__(self, analysis: ImportAnalysis, parent=None) -> None:
        super().__init__(parent)
        self.analysis = analysis
        package = analysis.package_info
        status_title, status_message, status_color = _STATUS_CONTENT[
            analysis.kind
        ]

        self.setWindowTitle(f"Import Package — {package.project_name}")
        self.setMinimumWidth(560)

        heading = QLabel("Review package import")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.status_label = QLabel(status_title)
        self.status_label.setStyleSheet(
            f"color: {status_color}; font-size: 16px; font-weight: bold;"
        )
        self.status_message = QLabel(status_message)
        self.status_message.setWordWrap(True)

        details = [
            f"Project: {package.project_name}",
            f"Game: {package.game_id}",
            f"Package version: {package.project_version}",
            f"Created by: {package.created_by}",
            f"Files: {package.file_count}",
        ]

        if analysis.local_version is not None:
            details.insert(
                3,
                f"Current local version: {analysis.local_version.version_number}",
            )

        if analysis.import_target is not None:
            details.append(f"Destination: {analysis.import_target}")

        if package.metadata.source_device_name:
            details.append(
                f"Source device: {package.metadata.source_device_name}"
            )

        game_version = package.metadata.game_metadata.get("game_version")

        if isinstance(game_version, str) and game_version.strip():
            details.append(f"Game version: {game_version.strip()}")

        if package.metadata.notes:
            details.append(f"Notes: {package.metadata.notes}")

        self.details_label = QLabel("\n".join(details))

        self.replace_confirmation = QCheckBox(
            "I understand that Save Shift will back up and replace the "
            "current save files."
        )
        self.replace_confirmation.setVisible(
            analysis.requires_replace_confirmation
        )

        self.import_button = QPushButton(
            "Replace With Backup"
            if analysis.requires_replace_confirmation
            else "Import Package"
        )
        self.import_button.setStyleSheet(styles.primary_button_style())
        self.import_button.setEnabled(
            not analysis.is_blocked
            and not analysis.requires_replace_confirmation
        )
        self.import_button.setVisible(not analysis.is_blocked)
        self.import_button.clicked.connect(self.accept)
        self.replace_confirmation.toggled.connect(
            self.import_button.setEnabled
        )

        cancel_button = QPushButton(
            "Close" if analysis.is_blocked else "Cancel"
        )
        cancel_button.setStyleSheet(styles.secondary_button_style())
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(self.import_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
        )
        layout.setSpacing(theme.SPACING)
        layout.addWidget(heading)
        layout.addWidget(self.status_label)
        layout.addWidget(self.status_message)
        layout.addWidget(self.details_label)
        layout.addWidget(self.replace_confirmation)
        layout.addLayout(button_row)
        self.setLayout(layout)
