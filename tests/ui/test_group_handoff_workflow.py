from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.coordination.manager import CoordinationManager
from app.coordination.models import LockLease
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.packages.package_info import PackageInfo
from app.services.hosting_service import HostingService
from app.services.import_conflict import ImportAnalysis, ImportConflictKind
from app.services.import_service import ImportService
from app.ui.main_window import MainWindow


PROJECT_UUID = "12345678-1234-5678-1234-567812345678"


class FakeProvider:
    def __init__(self) -> None:
        self.released: list[LockLease] = []

    def acquire_lock(self, project_uuid: str, owner: str) -> LockLease:
        now = datetime.now(UTC)
        return LockLease(
            project_uuid=project_uuid,
            lease_id="lease-1",
            fencing_token=1,
            owner_device_id="device-1",
            owner_display_name=owner,
            acquired_at_utc=now,
            expires_at_utc=now + timedelta(minutes=15),
        )

    def release_lock(self, lease: LockLease) -> None:
        self.released.append(lease)


class FakeHandoffController:
    running = False

    def __init__(self) -> None:
        self.publish_calls: list[tuple[Path, LockLease, object]] = []
        self.download_calls: list[tuple[str, object]] = []

    def publish(
        self,
        package_path: Path,
        lease: LockLease,
        provider: object,
    ) -> bool:
        self.publish_calls.append((package_path, lease, provider))
        return True

    def download_latest(self, project_uuid: str, provider: object) -> bool:
        self.download_calls.append((project_uuid, provider))
        return True


def _project(tmp_path: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        name="Shared World",
        local_path=str(tmp_path / "world"),
        uuid=PROJECT_UUID,
    )


def _installed_game(tmp_path: Path) -> InstalledGame:
    return InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )


def _version(package_path: Path, source_type: str = "HOSTED") -> ProjectVersion:
    return ProjectVersion(
        id=1,
        project_id=1,
        version_number=8,
        created_at_utc=datetime.now(UTC).replace(tzinfo=None),
        created_by="Bob",
        source_type=source_type,
        package_path=str(package_path),
        backup_path=str(package_path.parent / "backup"),
        package_checksum="a" * 64,
        parent_version_id=None,
        restored_from_version_id=None,
        lineage_name="main",
        notes=None,
    )


def _analysis(project: Project) -> ImportAnalysis:
    return ImportAnalysis(
        package_info=PackageInfo(
            package_format_version=1,
            project_uuid=project.uuid,
            project_version=8,
            game_id="abiotic_factor",
            project_name=project.name,
            created_at_utc="2026-08-11T12:00:00Z",
            created_by="Alice",
            save_shift_version="0.1.0-alpha.3",
            file_count=2,
            verified=True,
        ),
        project=project,
        local_version=None,
        kind=ImportConflictKind.FAST_FORWARD,
    )


def _window(qtbot, monkeypatch, tmp_path: Path) -> tuple[MainWindow, FakeProvider]:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.settings = replace(
        window.settings,
        coordination_enabled=True,
        player_display_name="Bob",
        coordination_device_name="Bob-PC",
    )
    provider = FakeProvider()
    window.coordination_manager = CoordinationManager(provider)
    window.package_handoff_controller = FakeHandoffController()
    window._get_installed_game_for_project = lambda _project: _installed_game(
        tmp_path
    )
    window.load_installed_games = lambda: None
    window.load_projects = lambda: None
    return window, provider


def test_group_project_card_uses_receive_and_handoff_labels(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    window, _provider = _window(qtbot, monkeypatch, tmp_path)

    card = window._create_project_card(
        _project(tmp_path),
        _installed_game(tmp_path),
    )

    assert card.import_button.text() == "Receive"
    assert card.export_button.text() == "Hand Off"


def test_handoff_publishes_version_then_releases_lease_on_success(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    window, provider = _window(qtbot, monkeypatch, tmp_path)
    project = _project(tmp_path)
    package_path = tmp_path / "hosted.sspkg"
    package_path.write_bytes(b"package")
    hosted_version = _version(package_path)
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )
    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: hosted_version,
    )

    window.handoff_project(project)

    controller = window.package_handoff_controller
    assert len(controller.publish_calls) == 1
    published_path, lease, published_provider = controller.publish_calls[0]
    assert published_path == package_path
    assert lease.project_uuid == project.uuid
    assert published_provider is provider
    assert provider.released == []

    window._group_handoff_published(object())

    assert provider.released == [lease]
    assert messages[0][0] == "Project Handed Off"
    assert "Version: 8" in messages[0][1]


def test_receive_downloads_previews_locks_and_imports(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    window, provider = _window(qtbot, monkeypatch, tmp_path)
    project = _project(tmp_path)
    package_path = tmp_path / "received.sspkg"
    package_path.write_bytes(b"package")
    analysis = _analysis(project)
    imported_version = _version(package_path, "IMPORTED")
    import_calls: list[dict[str, object]] = []
    messages: list[tuple[str, str]] = []

    class AcceptedDialog:
        def __init__(self, received_analysis, parent) -> None:
            assert received_analysis is analysis
            assert parent is window

        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "app.ui.main_window.ImportConflictDialog",
        AcceptedDialog,
    )
    monkeypatch.setattr(
        ImportService,
        "analyze_import",
        lambda _path: analysis,
    )
    monkeypatch.setattr(
        ImportService,
        "import_package",
        lambda **kwargs: (
            import_calls.append(kwargs) or imported_version
        ),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window.receive_or_import_project(project)

    controller = window.package_handoff_controller
    assert controller.download_calls == [(project.uuid, provider)]

    window._group_package_downloaded((object(), package_path))

    assert import_calls == [
        {
            "package_path": package_path,
            "imported_by": "Bob",
            "allow_replace": False,
        }
    ]
    assert len(provider.released) == 1
    assert provider.released[0].project_uuid == project.uuid
    assert package_path.exists()
    assert messages[0][0] == "Shared Package Received"


def test_failed_handoff_keeps_project_lease_for_safe_retry(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    window, provider = _window(qtbot, monkeypatch, tmp_path)
    project = _project(tmp_path)
    lease = window.coordination_manager.acquire_hosting_lease(
        project.uuid,
        "Bob",
    )
    window._pending_handoff_project = project
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.critical",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._group_handoff_failed("Steam is offline")

    assert provider.released == []
    assert window.coordination_manager.active_leases[project.uuid] == lease
    assert messages[0][0] == "Hand Off Failed"
