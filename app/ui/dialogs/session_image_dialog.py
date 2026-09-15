from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.ui import styles, theme
from app.ui.icons import apply_icon


class SessionImageDialog(QDialog):
    """Select an automatic game-window capture or a user-provided image."""

    def __init__(self, project_name: str, candidates: list[Path], parent=None) -> None:
        super().__init__(parent)
        self.selected_path: Path | None = None
        self.clear_requested = False
        self.setWindowTitle("Choose Session Image")
        self.setMinimumSize(720, 430)

        heading = QLabel(f"Choose an image for {project_name}")
        heading.setStyleSheet("font-size: 21px; font-weight: 600;")
        explanation = QLabel(
            "Save Shift captured only the visible game window. Choose one, "
            "select another image, or use no image for this session."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        self.candidate_list = QListWidget()
        self.candidate_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.candidate_list.setIconSize(QSize(240, 135))
        self.candidate_list.setGridSize(QSize(260, 175))
        self.candidate_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.candidate_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for index, path in enumerate(candidates, start=1):
            pixmap = QPixmap(str(path)).scaled(
                240,
                135,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            item = QListWidgetItem(QIcon(pixmap), f"Capture {index}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.candidate_list.addItem(item)
        if self.candidate_list.count():
            self.candidate_list.setCurrentRow(self.candidate_list.count() - 1)

        use_button = QPushButton("Use Selected")
        use_button.setStyleSheet(styles.primary_button_style())
        apply_icon(use_button, "camera", primary=True)
        use_button.setEnabled(bool(candidates))
        use_button.clicked.connect(self._use_selected)
        upload_button = QPushButton("Choose My Own…")
        upload_button.setStyleSheet(styles.secondary_button_style())
        apply_icon(upload_button, "upload")
        upload_button.clicked.connect(self._choose_file)
        none_button = QPushButton("No Image")
        none_button.setStyleSheet(styles.secondary_button_style())
        none_button.clicked.connect(self._clear)

        actions = QHBoxLayout()
        actions.addWidget(upload_button)
        actions.addWidget(none_button)
        actions.addStretch()
        actions.addWidget(use_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(heading)
        layout.addWidget(explanation)
        layout.addWidget(self.candidate_list, 1)
        layout.addLayout(actions)

    def _use_selected(self) -> None:
        item = self.candidate_list.currentItem()
        if item is None:
            return
        self.selected_path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        self.accept()

    def _choose_file(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Session Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if selected:
            self.selected_path = Path(selected)
            self.accept()

    def _clear(self) -> None:
        self.clear_requested = True
        self.accept()
