from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from app.coordination.models import CatalogPackage
from app.ui import styles, theme


class SharedProjectsDialog(QDialog):
    def __init__(
        self,
        packages: list[CatalogPackage],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.packages = packages
        self.setWindowTitle("Shared Projects")
        self.setMinimumSize(560, 360)

        heading = QLabel("Group Inbox")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        description = QLabel(
            "Choose a project shared by your group to download from Steam "
            "and import on this computer."
        )
        description.setWordWrap(True)

        self.project_list = QListWidget()
        for package in packages:
            metadata = package.metadata
            name = metadata.project_name if metadata else "Shared project"
            game = metadata.game_id if metadata else package.artifact.project_uuid
            self.project_list.addItem(
                f"{name}\n{game} · Version {package.artifact.project_version}"
            )

        self.receive_button = QPushButton("Receive Project")
        self.receive_button.setStyleSheet(styles.primary_button_style())
        self.receive_button.setEnabled(False)
        self.receive_button.clicked.connect(self.accept)
        self.project_list.currentRowChanged.connect(
            lambda row: self.receive_button.setEnabled(row >= 0)
        )
        self.project_list.itemDoubleClicked.connect(lambda _item: self.accept())

        close_button = QPushButton("Close")
        close_button.setStyleSheet(styles.secondary_button_style())
        close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close_button)
        buttons.addWidget(self.receive_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
        )
        layout.setSpacing(theme.SPACING)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(self.project_list)
        layout.addLayout(buttons)
        self.setLayout(layout)

    @property
    def selected_package(self) -> CatalogPackage | None:
        row = self.project_list.currentRow()
        return self.packages[row] if 0 <= row < len(self.packages) else None
