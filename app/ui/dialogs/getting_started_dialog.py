from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from app.ui import styles, theme


class GettingStartedDialog(QDialog):
    """A short, always-available explanation of Save Shift's group workflow."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("How Save Shift Works")
        self.setMinimumWidth(560)

        heading = QLabel("Share a world without overwriting each other")
        heading.setStyleSheet("font-size: 22px; font-weight: bold;")

        intro = QLabel(
            "Save Shift protects one shared copy of a world. Only the current "
            "host edits it; everyone else waits for the host to hand it off."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        steps = QLabel(
            "<b>1. Connect once</b><br>"
            "Create a group or paste an invitation from a friend. Save Shift "
            "then detects supported Steam games and checks for shared worlds.<br><br>"
            "<b>2. Receive before playing</b><br>"
            "Receive Shared World downloads a world that is not on this computer. "
            "For an existing world, Receive gets the group's newest version.<br><br>"
            "<b>3. Host when it is your turn</b><br>"
            "Host reserves the world for this computer and launches the game. "
            "Other members can join your game, but should not host their own copy.<br><br>"
            "<b>4. Hand off when finished</b><br>"
            "Exit the game, then choose Hand Off. Save Shift uploads the new "
            "version and makes the world available to the next host."
        )
        steps.setWordWrap(True)

        reminder = QLabel(
            "Simple rule: Receive → Host → play → exit the game → Hand Off."
        )
        reminder.setWordWrap(True)
        reminder.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: bold;")

        close_button = QPushButton("Got It")
        close_button.setStyleSheet(styles.primary_button_style())
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(theme.SPACING)
        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addSpacing(theme.SPACING_SMALL)
        layout.addWidget(steps)
        layout.addWidget(reminder)
        layout.addSpacing(theme.SPACING_SMALL)
        layout.addWidget(close_button)
        self.setLayout(layout)
