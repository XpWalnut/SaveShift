from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.packages.package_info import PackageInfo
from app.coordination.models import LockLease
from app.services.import_conflict import ImportAnalysis, ImportConflictKind
from app.services.import_service import ImportService
from app.ui.main_window import MainWindow
from app.ui.widgets.project_card import ProjectCard


def _project(tmp_path: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        name="Regression Test World",
        local_path=str(tmp_path / "world"),
        uuid="12345678-1234-5678-1234-567812345678",
    )


def _installed_game(tmp_path: Path) -> InstalledGame:
    return InstalledGame(
        id=1,
        game_id="abiotic_factor",
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "game-saves"),
        enabled=True,
    )


def _imported_version(package_path: Path) -> ProjectVersion:
    return ProjectVersion(
        id=1,
        project_id=1,
        version_number=4,
        created_at_utc=datetime.now(UTC).replace(tzinfo=None),
        created_by="Importing Player",
        source_type="IMPORTED",
        package_path=str(package_path),
        backup_path=str(package_path.parent / "backup"),
        package_checksum="a" * 64,
        parent_version_id=None,
        restored_from_version_id=None,
        lineage_name="main",
        notes=None,
    )


def _package_info(project_uuid: str) -> PackageInfo:
    return PackageInfo(
        package_format_version=1,
        project_uuid=project_uuid,
        project_version=4,
        game_id="abiotic_factor",
        project_name="Regression Test World",
        created_at_utc="2026-07-13T12:00:00Z",
        created_by="Exporting Player",
        save_shift_version="0.1.0-alpha.3",
        file_count=2,
        verified=True,
    )


def test_project_card_import_button_opens_global_import_workflow(
    qtbot,
    tmp_path: Path,
) -> None:
    import_calls: list[bool] = []
    project = _project(tmp_path)
    card = ProjectCard(
        project=project,
        installed_game=_installed_game(tmp_path),
        latest_version=None,
        on_host=lambda _project: None,
        on_import=lambda: import_calls.append(True),
        on_export=lambda _project: None,
        on_history=lambda _project: None,
    )
    qtbot.addWidget(card)

    qtbot.mouseClick(card.import_button, Qt.MouseButton.LeftButton)

    assert import_calls == [True]


def test_project_card_visibly_distinguishes_local_and_shared_worlds(
    qtbot,
    tmp_path: Path,
) -> None:
    local = ProjectCard(
        project=_project(tmp_path),
        installed_game=_installed_game(tmp_path),
        latest_version=None,
        on_host=lambda _project: None,
        on_import=lambda: None,
        on_export=lambda _project: None,
        on_history=lambda _project: None,
        on_share=lambda _project: None,
    )
    shared = ProjectCard(
        project=_project(tmp_path),
        installed_game=_installed_game(tmp_path),
        latest_version=None,
        on_host=lambda _project: None,
        on_import=lambda: None,
        on_export=lambda _project: None,
        on_history=lambda _project: None,
        group_name="Family Valheim",
    )
    qtbot.addWidget(local)
    qtbot.addWidget(shared)

    assert local.scope_badge.text() == "Local"
    assert local.share_button.isVisibleTo(local)
    assert shared.scope_badge.text() == "Shared · Family Valheim"
    assert not shared.share_button.isVisibleTo(shared)


def test_project_card_displays_lock_owner_and_expiration(
    qtbot,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    card = ProjectCard(
        project=_project(tmp_path),
        installed_game=_installed_game(tmp_path),
        latest_version=None,
        on_host=lambda _project: None,
        on_import=lambda: None,
        on_export=lambda _project: None,
        on_history=lambda _project: None,
    )
    qtbot.addWidget(card)
    lease = LockLease(
        project_uuid=card.project.uuid,
        lease_id="lease-123",
        fencing_token=1,
        owner_device_id="remote-device",
        owner_display_name="Alice",
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )

    card.show_lock(lease, local_device_id="local-device")

    assert "Locked by Alice" in card.lock_status_label.text()
    assert "Expires" in card.lock_status_label.text()
    assert "unless renewed" in card.lock_status_label.text()


def test_project_card_identifies_lock_owned_by_this_computer(
    qtbot,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    card = ProjectCard(
        project=_project(tmp_path),
        installed_game=_installed_game(tmp_path),
        latest_version=None,
        on_host=lambda _project: None,
        on_import=lambda: None,
        on_export=lambda _project: None,
        on_history=lambda _project: None,
    )
    qtbot.addWidget(card)
    lease = LockLease(
        project_uuid=card.project.uuid,
        lease_id="lease-123",
        fencing_token=1,
        owner_device_id="local-device",
        owner_display_name="Bob",
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )

    card.show_lock(lease, local_device_id="local-device")

    assert "Locked by Bob (this computer)" in card.lock_status_label.text()


def test_main_window_import_validates_then_imports_and_refreshes(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "incoming.sspkg"
    version = _imported_version(package_path)
    analysis_calls: list[Path] = []
    import_calls: list[dict[str, object]] = []
    messages: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.ui.main_window.discover_all_projects",
        lambda: None,
    )
    monkeypatch.setattr(
        ImportService,
        "analyze_import",
        lambda path: (
            analysis_calls.append(path)
            or ImportAnalysis(
                package_info=_package_info(
                    "12345678-1234-5678-1234-567812345678"
                ),
                project=None,
                local_version=None,
                kind=ImportConflictKind.NEW_PROJECT,
            )
        ),
    )

    class AcceptedImportDialog:
        def __init__(self, analysis: ImportAnalysis, parent) -> None:
            assert analysis.kind == ImportConflictKind.NEW_PROJECT
            assert parent is window

        def exec(self):
            return 1

    monkeypatch.setattr(
        "app.ui.main_window.ImportConflictDialog",
        AcceptedImportDialog,
    )

    def fake_import_package(**kwargs: object) -> ProjectVersion:
        import_calls.append(kwargs)
        return version

    monkeypatch.setattr(ImportService, "import_package", fake_import_package)
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("  Importing Player  ", True),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    refreshes: list[str] = []
    window.load_installed_games = lambda: refreshes.append("games")
    window.load_projects = lambda: refreshes.append("projects")

    window.import_package(package_path)

    assert analysis_calls == [package_path]
    assert import_calls == [
        {
            "package_path": package_path,
            "imported_by": "Importing Player",
            "allow_replace": False,
        }
    ]
    assert refreshes == ["games", "projects"]
    assert len(messages) == 1
    assert messages[0][0] == "Package Imported"
    assert "Version: 4" in messages[0][1]
    assert version.backup_path in messages[0][1]


def test_main_window_rejected_import_stops_before_prompt_or_import(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "duplicate.sspkg"
    warnings: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.ui.main_window.discover_all_projects",
        lambda: None,
    )

    def reject_import(_package_path: Path) -> None:
        raise ValueError("This package version has already been imported.")

    monkeypatch.setattr(
        ImportService,
        "analyze_import",
        reject_import,
    )
    monkeypatch.setattr(
        ImportService,
        "import_package",
        lambda **_kwargs: pytest.fail("import_package should not be called"),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: pytest.fail("Importer prompt should not open"),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    window = MainWindow()
    qtbot.addWidget(window)

    window.import_package(package_path)

    assert warnings == [
        (
            "Import Not Allowed",
            "This package version has already been imported.",
        )
    ]


def test_main_window_forwards_confirmed_divergent_replacement(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "diverged.sspkg"
    package_info = _package_info(
        "12345678-1234-5678-1234-567812345678"
    )
    project = _project(tmp_path)
    local_version = _imported_version(tmp_path / "current.sspkg")
    analysis = ImportAnalysis(
        package_info=package_info,
        project=project,
        local_version=local_version,
        kind=ImportConflictKind.DIVERGED,
    )
    import_calls: list[dict[str, object]] = []

    class AcceptedReplacementDialog:
        def __init__(self, received: ImportAnalysis, parent) -> None:
            assert received is analysis
            assert parent is window

        def exec(self):
            return 1

    monkeypatch.setattr(
        "app.ui.main_window.discover_all_projects",
        lambda: None,
    )
    monkeypatch.setattr(
        ImportService,
        "analyze_import",
        lambda _path: analysis,
    )
    monkeypatch.setattr(
        "app.ui.main_window.ImportConflictDialog",
        AcceptedReplacementDialog,
    )
    monkeypatch.setattr(
        ImportService,
        "import_package",
        lambda **kwargs: (
            import_calls.append(kwargs) or _imported_version(package_path)
        ),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Bob", True),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda *_args, **_kwargs: None,
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.load_installed_games = lambda: None
    window.load_projects = lambda: None

    window.import_package(package_path)

    assert import_calls == [
        {
            "package_path": package_path,
            "imported_by": "Bob",
            "allow_replace": True,
        }
    ]


def test_main_window_cancelled_preview_does_not_prompt_or_import(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "cancelled.sspkg"
    analysis = ImportAnalysis(
        package_info=_package_info(
            "12345678-1234-5678-1234-567812345678"
        ),
        project=None,
        local_version=None,
        kind=ImportConflictKind.NEW_PROJECT,
    )

    class RejectedImportDialog:
        def __init__(self, received: ImportAnalysis, _parent) -> None:
            assert received is analysis

        def exec(self):
            return 0

    monkeypatch.setattr(
        "app.ui.main_window.discover_all_projects",
        lambda: None,
    )
    monkeypatch.setattr(
        ImportService,
        "analyze_import",
        lambda _path: analysis,
    )
    monkeypatch.setattr(
        "app.ui.main_window.ImportConflictDialog",
        RejectedImportDialog,
    )
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: pytest.fail("name prompt must not open"),
    )
    monkeypatch.setattr(
        ImportService,
        "import_package",
        lambda **_kwargs: pytest.fail("package must not be imported"),
    )

    window = MainWindow()
    qtbot.addWidget(window)

    window.import_package(package_path)
