from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.games.game_id import GameId
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.restore_service import RestoreService
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.main_window import MainWindow


def _create_project(tmp_path: Path) -> Project:
    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(tmp_path / "game-saves"),
    )
    return ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="12345678-1234-5678-1234-567812345678",
        name="Regression World",
        local_path=tmp_path / "Regression World",
    )


def _create_version(
    project_id: int,
    version_number: int,
    *,
    source_type: str = ProjectVersionSource.HOSTED,
    restored_from_version_id: int | None = None,
    notes: str | None = None,
) -> ProjectVersion:
    return ProjectVersionService.create_version(
        project_id=project_id,
        created_by=f"Player {version_number}",
        source_type=source_type,
        version_number=version_number,
        restored_from_version_id=restored_from_version_id,
        notes=notes,
    )


def test_empty_history_disables_restore_button(qtbot, tmp_path: Path) -> None:
    project = _create_project(tmp_path)
    dialog = HistoryDialog(project=project, on_restore=lambda _version: None)
    qtbot.addWidget(dialog)

    assert dialog.version_list.count() == 1
    assert dialog.version_list.item(0).text() == "No versions have been recorded yet."
    assert not dialog.restore_button.isEnabled()


def test_history_lists_newest_first_with_notes_and_restore_origin(
    qtbot,
    tmp_path: Path,
) -> None:
    project = _create_project(tmp_path)
    first_version = _create_version(project.id, 1, notes="Initial host")
    _create_version(
        project.id,
        2,
        source_type=ProjectVersionSource.RESTORED,
        restored_from_version_id=first_version.id,
        notes="Returned to stable state",
    )
    dialog = HistoryDialog(project=project, on_restore=lambda _version: None)
    qtbot.addWidget(dialog)

    assert dialog.version_list.count() == 2
    newest_text = dialog.version_list.item(0).text()
    oldest_text = dialog.version_list.item(1).text()
    assert "Version 2" in newest_text
    assert "RESTORED by Player 2" in newest_text
    assert "Restored from Version 1" in newest_text
    assert "Notes: Returned to stable state" in newest_text
    assert "Version 1" in oldest_text
    assert "Notes: Initial host" in oldest_text
    assert dialog.version_list.currentRow() == 0


def test_history_restore_cancellation_does_not_invoke_callback(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project.id, 1)
    restore_calls: list[ProjectVersion] = []
    dialog = HistoryDialog(project=project, on_restore=restore_calls.append)
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
    )

    dialog._restore_selected_version()

    assert restore_calls == []
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_history_confirmed_restore_invokes_selected_version_and_closes(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    selected_version = _create_version(project.id, 1)
    restored_version = _create_version(
        project.id,
        2,
        source_type=ProjectVersionSource.RESTORED,
        restored_from_version_id=selected_version.id,
    )
    restore_calls: list[ProjectVersion] = []

    def restore(version: ProjectVersion) -> ProjectVersion:
        restore_calls.append(version)
        return restored_version

    dialog = HistoryDialog(project=project, on_restore=restore)
    qtbot.addWidget(dialog)
    dialog.version_list.setCurrentRow(1)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    dialog._restore_selected_version()

    assert len(restore_calls) == 1
    assert restore_calls[0].id == selected_version.id
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_main_window_restore_success_trims_name_reports_and_refreshes(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    source_version = _create_version(project.id, 1)
    restored_version = _create_version(
        project.id,
        2,
        source_type=ProjectVersionSource.RESTORED,
        restored_from_version_id=source_version.id,
    )
    restore_calls: list[dict[str, object]] = []
    messages: list[tuple[str, str]] = []

    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("  Restoring Player  ", True),
    )

    def fake_restore(**kwargs: object) -> ProjectVersion:
        restore_calls.append(kwargs)
        return restored_version

    monkeypatch.setattr(RestoreService, "restore", fake_restore)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    refreshes: list[bool] = []
    window.load_projects = lambda: refreshes.append(True)

    result = window.restore_version(project, source_version)

    assert result is restored_version
    assert restore_calls == [
        {
            "project_version": source_version,
            "restored_by": "Restoring Player",
        }
    ]
    assert refreshes == [True]
    assert len(messages) == 1
    assert messages[0][0] == "Version Restored"
    assert "New history version: 2" in messages[0][1]


def test_main_window_missing_restore_source_reports_error_without_refresh(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    source_version = _create_version(project.id, 1)
    errors: list[tuple[str, str]] = []

    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Restoring Player", True),
    )

    def missing_source(**_kwargs: object) -> ProjectVersion:
        raise FileNotFoundError("No restore source found.")

    monkeypatch.setattr(RestoreService, "restore", missing_source)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.critical",
        lambda _parent, title, message: errors.append((title, message)),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.load_projects = lambda: pytest.fail("projects should not refresh")

    result = window.restore_version(project, source_version)

    assert result is None
    assert errors == [("Restore Source Missing", "No restore source found.")]
