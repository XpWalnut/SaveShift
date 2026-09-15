from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.steam.social_client import SteamFriend


class SteamFriendDialog(QDialog):
    """Searchable Steam-friend picker for group invitations."""

    def __init__(
        self,
        friends: list[SteamFriend],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Invite a Steam Friend")
        self.setMinimumSize(460, 420)
        self._friends = sorted(
            friends,
            key=lambda friend: (friend.persona_name.casefold(), friend.steam_id),
        )

        description = QLabel(
            "Choose the friend to invite to this Save Shift group."
        )
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Steam friends…")
        self.friend_list = QListWidget()
        self.friend_list.itemDoubleClicked.connect(self.accept)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Invite")
        self.ok_button.setEnabled(False)

        self.search_input.textChanged.connect(self._populate)
        self.friend_list.currentItemChanged.connect(
            lambda current, _previous: self.ok_button.setEnabled(
                current is not None
            )
        )

        layout = QVBoxLayout(self)
        layout.addWidget(description)
        layout.addWidget(self.search_input)
        layout.addWidget(self.friend_list, 1)
        layout.addWidget(self.buttons)
        self._populate()

    @property
    def selected_friend(self) -> SteamFriend | None:
        item = self.friend_list.currentItem()
        if item is None:
            return None
        steam_id = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (friend for friend in self._friends if friend.steam_id == steam_id),
            None,
        )

    def _populate(self, query: str = "") -> None:
        needle = query.strip().casefold()
        selected_id = (
            self.selected_friend.steam_id
            if self.selected_friend is not None
            else ""
        )
        self.friend_list.clear()
        for friend in self._friends:
            label = f"{friend.persona_name}  ·  Steam …{friend.steam_id[-6:]}"
            if needle and needle not in label.casefold():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, friend.steam_id)
            self.friend_list.addItem(item)
            if friend.steam_id == selected_id:
                self.friend_list.setCurrentItem(item)
        if self.friend_list.currentItem() is None and self.friend_list.count():
            self.friend_list.setCurrentRow(0)

