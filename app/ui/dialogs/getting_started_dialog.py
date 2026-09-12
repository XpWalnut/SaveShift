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
            "<b>1. Choose the right group</b><br>"
            "Create or join as many groups as you need, then select the group "
            "for the friends and worlds you are playing with.<br><br>"
            "<b>2. Share or receive once</b><br>"
            "Local worlds stay only on this computer. Use Share to associate "
            "one with the active group. Receive Shared World adds a group world "
            "that is not on this computer yet.<br><br>"
            "<b>3. Let Host synchronize</b><br>"
            "After the world is on this computer, Host receives the active "
            "group's latest version automatically before launching the game.<br><br>"
            "<b>4. Host when it is your turn</b><br>"
            "Host reserves the world, receives the latest version, and launches "
            "the game. "
            "Other members can join your game, but should not host their own copy.<br><br>"
            "<b>5. Exit the game when finished</b><br>"
            "Keep Save Shift open. When the game closes, Save Shift uploads the "
            "new version and releases the world for the next host automatically. "
            "Manual Receive and Hand Off controls can be enabled in Settings."
        )
        steps.setWordWrap(True)

        reminder = QLabel(
            "Simple rule: Receive once → Host → play → exit the game."
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
