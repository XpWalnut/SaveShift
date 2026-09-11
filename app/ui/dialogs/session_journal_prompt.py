from PySide6.QtWidgets import QCheckBox, QMessageBox


class SessionJournalPrompt(QMessageBox):
    def __init__(self, project_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setIcon(QMessageBox.Icon.Question)
        self.setWindowTitle("Add to World Journal?")
        self.setText(
            f"Would you like to record what happened during this session "
            f"in {project_name}'s World Journal?"
        )
        self.setInformativeText(
            "You can also add an entry later from the project card."
        )
        self.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        self.setDefaultButton(QMessageBox.StandardButton.Yes)

        self.dont_ask_again_checkbox = QCheckBox(
            "Don't ask me again after hosted sessions"
        )
        self.setCheckBox(self.dont_ask_again_checkbox)

    @property
    def dont_ask_again(self) -> bool:
        return self.dont_ask_again_checkbox.isChecked()
