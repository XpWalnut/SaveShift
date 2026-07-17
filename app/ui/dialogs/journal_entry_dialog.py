from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.packages.package_journal_entry import (
    MAX_JOURNAL_BODY_LENGTH,
    MAX_JOURNAL_TITLE_LENGTH,
)
from app.ui import theme


class JournalEntryDialog(QDialog):
    def __init__(self, project_name: str, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle(f"Add to World Journal — {project_name}")
        self.setMinimumSize(520, 400)

        heading = QLabel("What happened in this session?")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")

        description = QLabel(
            "Record accomplishments, discoveries, challenges, or plans for "
            "the next host. This entry will travel with future handoffs."
        )
        description.setWordWrap(True)
        description.setObjectName("SecondaryText")

        title_label = QLabel("Title")
        self.title_input = QLineEdit()
        self.title_input.setMaxLength(MAX_JOURNAL_TITLE_LENGTH)
        self.title_input.setPlaceholderText("Built our first portal hub")

        body_label = QLabel("Journal entry")
        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText(
            "Summarize what the group accomplished and what comes next…"
        )

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.setContentsMargins(
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
            theme.SPACING_LARGE,
        )
        layout.setSpacing(theme.SPACING_SMALL)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addSpacing(theme.SPACING_SMALL)
        layout.addWidget(title_label)
        layout.addWidget(self.title_input)
        layout.addWidget(body_label)
        layout.addWidget(self.body_input, 1)
        layout.addWidget(self.buttons)
        self.setLayout(layout)

    @property
    def entry_title(self) -> str:
        return self.title_input.text().strip()

    @property
    def entry_body(self) -> str:
        return self.body_input.toPlainText().strip()

    def _validate_and_accept(self) -> None:
        if not self.entry_title:
            QMessageBox.warning(self, "Title Required", "Enter a journal title.")
            return

        if not self.entry_body:
            QMessageBox.warning(
                self,
                "Journal Entry Required",
                "Describe what happened during the session.",
            )
            return

        if len(self.entry_body) > MAX_JOURNAL_BODY_LENGTH:
            QMessageBox.warning(
                self,
                "Journal Entry Too Long",
                f"Journal entries cannot exceed {MAX_JOURNAL_BODY_LENGTH} "
                "characters.",
            )
            return

        self.accept()
