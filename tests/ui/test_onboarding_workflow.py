from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from PySide6.QtWidgets import QLabel

from app.coordination.models import GroupInvitation, PairedDevice
from app.ui.dialogs.getting_started_dialog import GettingStartedDialog
from app.ui.main_window import MainWindow


def _window(qtbot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_home_screen_surfaces_group_setup_and_help(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)

    assert not window.create_group_button.isHidden()
    assert not window.join_group_button.isHidden()
    assert window.shared_projects_button.isHidden()
    assert "invitation" in window.join_group_button.toolTip()
    assert "Receive" in window.how_it_works_button.toolTip()


def test_first_launch_silently_detects_steam_games(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    calls: list[bool] = []
    monkeypatch.delenv("SAVESHIFT_DISABLE_GAME_DETECTION")
    monkeypatch.setattr(
        window,
        "_detect_steam_games",
        lambda *, show_messages: calls.append(show_messages) or [],
    )

    window._start_automatic_game_detection()

    assert calls == [False]


def test_connected_home_screen_surfaces_invite_and_shared_worlds(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = replace(
        window.settings,
        coordination_enabled=True,
        coordination_is_administrator=True,
    )

    window._refresh_group_buttons()

    assert window.create_group_button.isHidden()
    assert window.join_group_button.isHidden()
    assert not window.invite_friend_button.isHidden()
    assert not window.shared_projects_button.isHidden()


def test_home_join_uses_saved_name_and_computer_name(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = replace(
        window.settings,
        player_display_name="Hunter",
        coordination_device_name="Hunter PC",
    )
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(window, "_begin_join_group", lambda *args: calls.append(args))

    window.join_group_from_home()

    assert calls == [("Hunter PC", "Hunter")]


def test_join_completion_detects_games_then_opens_shared_worlds(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window._pending_coordination_profile_name = "Hunter"
    window._pending_coordination_device_name = "Hunter PC"
    calls: list[str] = []

    def apply_settings(settings) -> bool:
        window.settings = settings
        calls.append("settings")
        return True

    monkeypatch.setattr(window, "_apply_coordination_settings", apply_settings)
    monkeypatch.setattr(
        window,
        "_detect_steam_games",
        lambda *, show_messages: calls.append(f"detect:{show_messages}") or [],
    )
    monkeypatch.setattr(window, "show_shared_projects", lambda: calls.append("shared"))
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda *_args: calls.append("message"),
    )
    invitation = GroupInvitation(
        provider_url="https://group.example.workers.dev",
        invitation_token="invite-token",
        expires_at_utc=datetime.now(UTC) + timedelta(hours=1),
    )

    window._group_joined(
        invitation,
        PairedDevice("device-1", "device-token"),
    )

    assert calls == ["settings", "message", "detect:False", "shared"]


def test_getting_started_explains_complete_host_cycle(qtbot) -> None:
    dialog = GettingStartedDialog()
    qtbot.addWidget(dialog)
    text = " ".join(
        label.text()
        for label in dialog.findChildren(QLabel)
    )

    assert "Receive" in text
    assert "Host" in text
    assert "Hand Off" in text
