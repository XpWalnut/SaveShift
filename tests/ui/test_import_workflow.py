from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
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


def test_main_window_import_validates_then_imports_and_refreshes(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "incoming.sspkg"
    version = _imported_version(package_path)
    validation_calls: list[Path] = []
    import_calls: list[dict[str, object]] = []
    messages: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.ui.main_window.discover_all_projects",
        lambda: None,
    )
    monkeypatch.setattr(
        ImportService,
        "validate_import_package",
        lambda path: validation_calls.append(path),
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

    assert validation_calls == [package_path]
    assert import_calls == [
        {
            "package_path": package_path,
            "imported_by": "Importing Player",
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
        "validate_import_package",
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
