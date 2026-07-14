from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from app.coordination.errors import LockConflictError, LockOwnershipError
from app.coordination.manager import CoordinationManager
from app.coordination.models import LockLease, PairedDevice
from app.core.settings import AppSettings
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.services.hosting_service import HostingService
from app.ui.main_window import MainWindow


PROJECT_UUID = "12345678-1234-4678-9234-567812345678"


def _lease(owner: str = "Jake") -> LockLease:
    now = datetime.now(UTC)
    return LockLease(
        project_uuid=PROJECT_UUID,
        lease_id="lease-123",
        fencing_token=1,
        owner_device_id="device-123",
        owner_display_name=owner,
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )


class FakeProvider:
    def __init__(self) -> None:
        self.acquired: list[tuple[str, str]] = []
        self.released: list[LockLease] = []
        self.acquire_error: Exception | None = None
        self.renew_error: Exception | None = None

    def acquire_lock(self, project_uuid: str, owner: str) -> LockLease:
        if self.acquire_error is not None:
            raise self.acquire_error

        self.acquired.append((project_uuid, owner))
        return _lease(owner)

    def renew_lock(self, lease: LockLease) -> LockLease:
        if self.renew_error is not None:
            raise self.renew_error

        return lease

    def release_lock(self, lease: LockLease) -> None:
        self.released.append(lease)


def _window(qtbot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.settings = replace(window.settings, coordination_enabled=True)
    return window


def _project(tmp_path: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        name="Test World",
        local_path=str(tmp_path / "world"),
        uuid=PROJECT_UUID,
    )


def test_configured_settings_create_provider_neutral_manager() -> None:
    settings = AppSettings(
        coordination_enabled=True,
        coordination_server_url="https://locks.example.com",
        coordination_device_id="device-123",
        coordination_device_token="secret-token",
    )

    manager = MainWindow._create_coordination_manager(settings)

    assert manager is not None
    assert manager.provider.base_url == "https://locks.example.com"
    assert manager.provider.device_token == "secret-token"


def test_player_name_is_requested_once_then_reused(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings()
    prompts: list[bool] = []
    saved_settings: list[AppSettings] = []
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: (
            prompts.append(True) or "  Alice  ",
            True,
        ),
    )
    monkeypatch.setattr(
        "app.ui.main_window.SettingsService.save",
        saved_settings.append,
    )

    assert window._get_player_display_name() == "Alice"
    assert window._get_player_display_name() == "Alice"
    assert prompts == [True]
    assert saved_settings[0].player_display_name == "Alice"


def test_settings_pair_device_and_rebuild_manager(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings()
    saved_settings: list[AppSettings] = []
    pair_calls: list[tuple[str, str, str]] = []

    class AcceptedSettingsDialog:
        automatic_update_checks = True
        player_display_name = "Jake"
        coordination_enabled = True
        coordination_server_url = "https://locks.example.com"
        coordination_device_name = "Gaming PC"
        coordination_pairing_code = "pair-code"
        check_requested = False

        def __init__(self, **_kwargs) -> None:
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    class PairingProvider:
        def __init__(self, base_url: str, device_token: str | None = None) -> None:
            self.base_url = base_url
            self.device_token = device_token

        def pair(self, pairing_code: str, device_name: str) -> PairedDevice:
            pair_calls.append((self.base_url, pairing_code, device_name))
            return PairedDevice("device-123", "secret-token")

    monkeypatch.setattr(
        "app.ui.main_window.SettingsDialog",
        AcceptedSettingsDialog,
    )
    monkeypatch.setattr(
        "app.ui.main_window.HttpCoordinationProvider",
        PairingProvider,
    )
    monkeypatch.setattr(
        "app.ui.main_window.SettingsService.save",
        saved_settings.append,
    )

    window.show_settings()

    assert pair_calls == [
        ("https://locks.example.com", "pair-code", "Gaming PC")
    ]
    assert saved_settings[0].coordination_device_id == "device-123"
    assert saved_settings[0].coordination_device_token == "secret-token"
    assert saved_settings[0].player_display_name == "Jake"
    assert window.coordination_manager is not None


def test_host_conflict_blocks_local_hosting_workflow(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    provider = FakeProvider()
    provider.acquire_error = LockConflictError(
        "Project is already locked.",
        lock=_lease("Alex"),
    )
    window.coordination_manager = CoordinationManager(provider)
    warnings: list[tuple[str, str]] = []
    installed_game = InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )

    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Jake", True),
    )
    monkeypatch.setattr(
        window,
        "_get_installed_game_for_project",
        lambda _project: installed_game,
    )
    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: pytest.fail("save files must not be changed"),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    window.host_project(_project(tmp_path))

    assert warnings[0][0] == "Project In Use"
    assert "Alex" in warnings[0][1]


def test_temporary_ui_lease_is_released_when_operation_fails(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    provider = FakeProvider()
    window.coordination_manager = CoordinationManager(provider)

    with pytest.raises(ValueError, match="operation failed"):
        with window._temporary_coordination_lease(PROJECT_UUID, "Jake"):
            assert window.coordination_manager.has_active_lease(PROJECT_UUID)
            raise ValueError("operation failed")

    assert provider.acquired == [(PROJECT_UUID, "Jake")]
    assert [lease.project_uuid for lease in provider.released] == [PROJECT_UUID]
    assert not window.coordination_manager.active_leases


def test_lost_lease_is_forgotten_and_warns_user_to_stop_game(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    provider = FakeProvider()
    provider.renew_error = LockOwnershipError("Lease expired.")
    manager = CoordinationManager(provider)
    manager.acquire_hosting_lease(PROJECT_UUID, "Jake")
    window.coordination_manager = manager
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.critical",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._renew_coordination_leases()

    assert not manager.active_leases
    assert messages[0][0] == "Project Lock Lost"
    assert "Stop the game now" in messages[0][1]
