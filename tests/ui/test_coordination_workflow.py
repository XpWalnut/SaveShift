from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.coordination.errors import LockConflictError, LockOwnershipError
from app.coordination.manager import CoordinationManager
from app.coordination.models import LockLease, PairedDevice
from app.coordination.cloudflare_provisioning import CreatedGroup
from app.coordination.setup_controller import GroupLeaveOutcome
from app.core.settings import (
    AppSettings,
    CoordinationGroupSettings,
    SettingsService,
)
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.repositories.project_repository import ProjectRepository
from app.services.hosting_service import HostingService
from app.ui.main_window import MainWindow
from app.ui.widgets.project_card import ProjectCard
from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_invitation import JoinedSteamGroup
from app.steam.native_group_service import CreatedSteamGroup
from app.steam.group_manifest import SteamGroupManifest
from tests.steam.test_device_identity import MemoryProtector


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


def test_switching_groups_rebuilds_manager_with_selected_credentials(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    family = CoordinationGroupSettings(
        group_id="family",
        name="Family",
        server_url="https://family.example",
        device_id="family-device",
        device_token="family-token",
    )
    friends = CoordinationGroupSettings(
        group_id="friends",
        name="Friends",
        server_url="https://friends.example",
        device_id="friends-device",
        device_token="friends-token",
    )
    window.settings = AppSettings(
        coordination_groups=(family, friends),
    ).with_active_group("family")
    window.coordination_manager = MainWindow._create_coordination_manager(
        window.settings
    )
    saved: list[AppSettings] = []
    monkeypatch.setattr(SettingsService, "save", saved.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_refresh_project_lock_statuses", lambda: None)

    assert window._switch_active_group("friends")

    assert saved[-1].active_coordination_group_id == "friends"
    assert window.coordination_manager is not None
    assert window.coordination_manager.provider.base_url == "https://friends.example"
    assert window.coordination_manager.provider.device_token == "friends-token"


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


def test_created_group_is_saved_as_cloudflare_administrator(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings()
    window._pending_coordination_profile_name = "Alice"
    window._pending_coordination_device_name = "Alice PC"
    saved_settings: list[AppSettings] = []
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(SettingsService, "save", saved_settings.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_refresh_project_lock_statuses", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._group_created(
        CreatedGroup(
            provider_url="https://group.workers.dev",
            account_id="account-123",
            script_name="saveshift-coordination-123",
            device=PairedDevice("device-123", "device-token", True),
        )
    )

    assert saved_settings[0].coordination_enabled is True
    assert saved_settings[0].coordination_is_administrator is True
    assert saved_settings[0].coordination_provider_kind == "cloudflare"
    assert saved_settings[0].player_display_name == "Alice"
    assert window.coordination_manager is not None
    assert messages[0][0] == "Group Created"


def test_created_steam_group_is_persisted_without_cloudflare_credentials(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings()
    window._pending_coordination_profile_name = "Alice"
    window._pending_coordination_device_name = "Alice PC"
    identity = SteamDeviceIdentityStore(
        tmp_path / "identity.json", protector=MemoryProtector()
    ).load_or_create("76561198000000001")
    manifest, _ = SteamGroupManifest.create("Family Worlds", identity)
    saved: list[AppSettings] = []
    messages: list[str] = []
    monkeypatch.setattr(SettingsService, "save", saved.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_refresh_project_lock_statuses", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, _message: messages.append(title),
    )

    window._steam_group_created(
        CreatedSteamGroup(manifest, "3797671909", identity, "3797671910")
    )

    group = saved[0].active_coordination_group
    assert group is not None
    assert group.provider_kind == "steam"
    assert group.group_id == manifest.group_id
    assert group.steam_manifest_item_id == "3797671909"
    assert group.steam_package_index_item_id == "3797671910"
    assert group.server_url == ""
    assert group.device_token == ""
    assert window.coordination_manager is not None
    assert messages == ["Steam Group Created"]


def test_steam_group_invitation_uses_steam_controller(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    group = CoordinationGroupSettings(
        group_id="steam-group",
        name="Friends",
        device_id="device-123",
        is_administrator=True,
        provider_kind="steam",
        steam_manifest_item_id="3797671909",
    )
    window.settings = AppSettings().upsert_group(group)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(window, "_show_group_setup_progress", lambda _text: None)
    monkeypatch.setattr(
        window.group_setup_controller,
        "invite_steam_member",
        lambda item_id, group_id: calls.append((item_id, group_id)) or True,
    )

    window._create_group_invitation()

    assert calls == [("3797671909", "steam-group")]


def test_joined_steam_group_is_persisted_for_the_enrolled_device(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings()
    window._pending_coordination_profile_name = "Hunter"
    window._pending_coordination_device_name = "Hunter PC"
    administrator = SteamDeviceIdentityStore(
        tmp_path / "administrator.json", protector=MemoryProtector()
    ).load_or_create("76561198000000001")
    member = SteamDeviceIdentityStore(
        tmp_path / "member.json", protector=MemoryProtector()
    ).load_or_create("76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Valheim Crew", administrator)
    manifest = manifest.add_member(
        member,
        group_key,
        administrator,
        package_index_item_id="3797671910",
    )
    saved: list[AppSettings] = []
    messages: list[str] = []
    monkeypatch.setattr(SettingsService, "save", saved.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_detect_steam_games", lambda **_kwargs: None)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, _message: messages.append(title),
    )

    window._steam_group_joined(
        JoinedSteamGroup(
            manifest_item_id="3797671909",
            manifest=manifest,
            group_key=group_key,
            device_id=member.device_id,
            steam_id=member.steam_id,
        )
    )

    group = saved[0].active_coordination_group
    assert group is not None
    assert group.provider_kind == "steam"
    assert group.device_id == member.device_id
    assert group.is_administrator is False
    assert group.name == "Valheim Crew"
    assert group.steam_package_index_item_id == "3797671910"
    assert messages == ["Steam Group Joined"]


def test_unsharing_steam_world_only_removes_its_local_group_association(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    group = CoordinationGroupSettings(
        group_id="steam-group",
        name="Friends",
        device_id="device-123",
        is_administrator=True,
        provider_kind="steam",
        steam_manifest_item_id="3797671909",
    )
    window.settings = AppSettings().upsert_group(group)
    project = _project(tmp_path)
    project.coordination_group_id = group.group_id
    associations: list[tuple[int, str | None]] = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        ProjectRepository,
        "associate_group",
        lambda pid, gid: associations.append((pid, gid)),
    )
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(
        window.group_setup_controller,
        "invite_steam_member",
        lambda *_args: pytest.fail("Unsharing must not open a Steam invitation."),
    )

    window._unshare_project(project)

    assert associations == [(project.id, None)]


def test_leaving_group_clears_local_coordination_credentials(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings(
        player_display_name="Alice",
        coordination_enabled=True,
        coordination_server_url="https://group.workers.dev",
        coordination_device_id="device-123",
        coordination_device_name="Alice PC",
        coordination_device_token="device-token",
        coordination_is_administrator=True,
        coordination_provider_kind="cloudflare",
        coordination_cloudflare_account_id="account-123",
        coordination_cloudflare_script_name="saveshift-coordination-123",
    )
    saved_settings: list[AppSettings] = []
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(SettingsService, "save", saved_settings.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_refresh_project_lock_statuses", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._group_left(GroupLeaveOutcome(True, True, ""))

    saved = saved_settings[0]
    assert saved.player_display_name == "Alice"
    assert saved.coordination_enabled is False
    assert saved.coordination_server_url == ""
    assert saved.coordination_device_id == ""
    assert saved.coordination_device_token == ""
    assert saved.coordination_cloudflare_account_id == ""
    assert messages == [
        ("Group Left", "The empty group and its Cloudflare provider were removed.")
    ]


def test_member_can_forget_legacy_group_when_leave_endpoint_is_unavailable(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings(
        coordination_enabled=True,
        coordination_server_url="https://legacy-group.workers.dev",
        coordination_device_id="device-123",
        coordination_device_token="device-token",
        coordination_is_administrator=False,
    )
    window._leaving_group = True
    saved_settings: list[AppSettings] = []
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(SettingsService, "save", saved_settings.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_refresh_project_lock_statuses", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._group_setup_failed("The coordination provider returned HTTP 404.")

    assert saved_settings[0].coordination_enabled is False
    assert saved_settings[0].coordination_device_token == ""
    assert messages == [
        ("Group Forgotten", "This computer is no longer configured to use the group.")
    ]


def test_legacy_group_administrator_claim_is_persisted(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings(
        coordination_enabled=True,
        coordination_server_url="https://group.workers.dev",
        coordination_device_id="legacy-device",
        coordination_device_token="legacy-token",
        coordination_device_name="Owner PC",
    )
    claims: list[str] = []
    saved_settings: list[AppSettings] = []
    messages: list[tuple[str, str]] = []

    class LegacyProvider:
        def __init__(self, base_url: str, device_token: str | None = None):
            assert base_url == "https://group.workers.dev"
            assert device_token == "legacy-token"

        def claim_administrator(self, pairing_code: str) -> None:
            claims.append(pairing_code)

    monkeypatch.setattr(
        "app.ui.main_window.HttpCoordinationProvider",
        LegacyProvider,
    )
    monkeypatch.setattr(SettingsService, "save", saved_settings.append)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(window, "_refresh_project_lock_statuses", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._claim_group_administrator("old-pair-code")

    assert claims == ["old-pair-code"]
    assert saved_settings[0].coordination_is_administrator is True
    assert window.settings.coordination_is_administrator is True
    assert messages[0][0] == "Administrator Access Enabled"


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


def test_host_refuses_to_sync_while_game_is_already_running(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = replace(window.settings, player_display_name="Jake")
    provider = FakeProvider()
    window.coordination_manager = CoordinationManager(provider)
    project = _project(tmp_path)
    installed_game = InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )
    warnings: list[tuple[str, str]] = []

    class RunningGame:
        display_name = "Abiotic Factor"

        @staticmethod
        def is_running() -> bool:
            return True

    monkeypatch.setattr(
        window,
        "_get_installed_game_for_project",
        lambda _project: installed_game,
    )
    monkeypatch.setattr(
        "app.ui.main_window.GameRegistry.get_by_game_id",
        lambda _game_id: RunningGame(),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    window.host_project(project)

    assert provider.acquired == []
    assert warnings[0][0] == "Close Game Before Hosting"
    assert "receive the latest group version" in warnings[0][1]


def test_host_acquires_lock_and_launches_without_creating_version(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = replace(
        window.settings,
        player_display_name="Jake",
        manual_transfer_controls=True,
    )
    provider = FakeProvider()
    window.coordination_manager = CoordinationManager(provider)
    project = _project(tmp_path)
    installed_game = InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )
    launches: list[bool] = []
    messages: list[tuple[str, str]] = []

    class FakeGame:
        display_name = "Abiotic Factor"

        @staticmethod
        def is_running() -> bool:
            return False

        @staticmethod
        def launch() -> None:
            launches.append(True)

    monkeypatch.setattr(
        window,
        "_get_installed_game_for_project",
        lambda _project: installed_game,
    )
    monkeypatch.setattr(
        "app.ui.main_window.GameRegistry.get_by_game_id",
        lambda _game_id: FakeGame(),
    )
    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: pytest.fail("Host must not create a project version"),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )
    downloads: list[tuple[str, object]] = []
    monkeypatch.setattr(
        window.package_handoff_controller,
        "download_latest",
        lambda project_uuid, selected_provider: (
            downloads.append((project_uuid, selected_provider)) or True
        ),
    )

    window.host_project(project)
    window._group_package_downloaded(None)

    assert provider.acquired == [(PROJECT_UUID, "Jake")]
    assert downloads == [(PROJECT_UUID, provider)]
    assert window.coordination_manager.has_active_lease(PROJECT_UUID)
    assert launches == [True]
    assert messages[0][0] == "Project Hosted"
    assert "latest group version was received first" in messages[0][1]

    window._release_coordination_lease(PROJECT_UUID, report_error=False)


def test_remote_project_lock_changes_host_action_to_join_game(
    qtbot,
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    installed_game = InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )
    joined: list[Project] = []
    card = ProjectCard(
        project=project,
        installed_game=installed_game,
        latest_version=None,
        on_host=lambda _project: pytest.fail("remote project cannot be hosted"),
        on_import=lambda: None,
        on_export=lambda _project: None,
        on_history=lambda _project: None,
        on_join=joined.append,
    )
    qtbot.addWidget(card)

    card.show_lock(_lease("Alex"), local_device_id="local-device")

    assert card.host_button.text() == "Join Game"
    assert card.host_button.isEnabled()
    card.host_button.click()
    assert joined == [project]


def test_join_hosted_project_launches_game_without_touching_save(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.settings = replace(
        window.settings,
        coordination_device_id="local-device",
    )
    project = _project(tmp_path)
    lease = _lease("Alex")
    window.project_lock_statuses[project.uuid] = lease
    installed_game = InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )
    launches: list[bool] = []
    messages: list[tuple[str, str]] = []

    class FakeGame:
        display_name = "Abiotic Factor"

        @staticmethod
        def is_running() -> bool:
            return False

        @staticmethod
        def join_hosted_session() -> None:
            launches.append(True)

    monkeypatch.setattr(
        window,
        "_get_installed_game_for_project",
        lambda _project: installed_game,
    )
    monkeypatch.setattr(
        "app.ui.main_window.GameRegistry.get_by_game_id",
        lambda _game_id: FakeGame(),
    )
    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: pytest.fail("joining must not create a hosted version"),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window.join_hosted_project(project)

    assert launches == [True]
    assert messages[0][0] == "Join Hosted Game"
    assert "Alex is hosting" in messages[0][1]
    assert "will not import or modify" in messages[0][1]


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
