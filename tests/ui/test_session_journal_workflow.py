from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.database.models.session_journal_entry import SessionJournalEntry
from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.games.game_id import GameId
from app.services.project_service import ProjectService
from app.services.session_journal_service import SessionJournalService
from app.services.export_service import ExportService
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.main_window import MainWindow
from app.ui.widgets.project_card import ProjectCard


def _detached_project(tmp_path: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        name="Journal World",
        local_path=str(tmp_path / "world"),
        uuid="12345678-1234-5678-1234-567812345678",
    )


def _detached_game(tmp_path: Path) -> InstalledGame:
    return InstalledGame(
        id=1,
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(tmp_path / "saves"),
        enabled=True,
    )


def _stored_project(tmp_path: Path) -> Project:
    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(tmp_path / "saves"),
    )
    return ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="12345678-1234-5678-1234-567812345678",
        name="Journal World",
        local_path=tmp_path / "world",
    )


def test_project_card_previews_latest_journal_and_opens_journal(
    qtbot,
    tmp_path: Path,
) -> None:
    project = _detached_project(tmp_path)
    latest = SessionJournalEntry(
        id=1,
        entry_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        project_id=project.id,
        title="Portal network complete",
        body="Every base is now connected.",
        created_by="Alice",
        created_at_utc=datetime(2026, 7, 15, 12, tzinfo=UTC),
    )
    journal_calls: list[Project] = []
    card = ProjectCard(
        project=project,
        installed_game=_detached_game(tmp_path),
        latest_version=None,
        on_host=lambda _project: None,
        on_import=lambda: None,
        on_export=lambda _project: None,
        on_history=lambda _project: None,
        latest_journal=latest,
        on_journal=journal_calls.append,
    )
    qtbot.addWidget(card)

    assert "Portal network complete" in card.journal_preview_label.text()
    assert "Alice" in card.journal_preview_label.text()
    qtbot.mouseClick(card.journal_button, Qt.MouseButton.LeftButton)
    assert journal_calls == [project]


def test_history_journal_tab_lists_newest_first_and_reloads_after_add(
    qtbot,
    tmp_path: Path,
) -> None:
    project = _stored_project(tmp_path)
    SessionJournalService.create_entry(
        project_id=project.id,
        title="First shelter",
        body="The group survived the first night.",
        created_by="Alice",
        created_at_utc=datetime(2026, 7, 15, 12, tzinfo=UTC),
        project_version_number=1,
    )

    def add_entry():
        return SessionJournalService.create_entry(
            project_id=project.id,
            title="Boss defeated",
            body="The group claimed its first trophy.",
            created_by="Bob",
            created_at_utc=datetime(2026, 7, 15, 14, tzinfo=UTC),
            project_version_number=2,
        )

    dialog = HistoryDialog(
        project=project,
        on_restore=lambda _version: None,
        on_add_journal=add_entry,
        initial_tab="journal",
    )
    qtbot.addWidget(dialog)

    assert dialog.tabs.tabText(dialog.tabs.currentIndex()) == "World Journal"
    assert dialog.journal_list.count() == 1
    assert "First shelter" in dialog.journal_list.item(0).text()

    qtbot.mouseClick(dialog.add_journal_button, Qt.MouseButton.LeftButton)

    assert dialog.journal_list.count() == 2
    assert "Boss defeated" in dialog.journal_list.item(0).text()
    assert "Version 2" in dialog.journal_list.item(0).text()
    assert "First shelter" in dialog.journal_list.item(1).text()


def test_export_handoff_forwards_optional_journal_entry(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = _detached_project(tmp_path)
    installed_game = _detached_game(tmp_path)
    destination = tmp_path / "handoff.sspkg"
    export_calls: list[dict[str, object]] = []

    class AcceptedJournalDialog:
        entry_title = "New outpost"
        entry_body = "The group established a mountain base."

        def __init__(self, project_name: str, parent) -> None:
            assert project_name == project.name
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), ""),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.ui.main_window.JournalEntryDialog",
        AcceptedJournalDialog,
    )

    def fake_export(**kwargs: object):
        export_calls.append(kwargs)
        return SimpleNamespace(version_number=3)

    monkeypatch.setattr(ExportService, "export_project", fake_export)

    window = MainWindow()
    qtbot.addWidget(window)
    window._get_installed_game_for_project = lambda _project: installed_game
    window._get_player_display_name = lambda: "Alice"
    window.load_installed_games = lambda: None
    window.load_projects = lambda: None

    window.export_project(project)

    assert export_calls == [
        {
            "project": project,
            "game_id": installed_game.game_id,
            "exported_by": "Alice",
            "destination_path": destination,
                "journal_title": "New outpost",
                "journal_body": "The group established a mountain base.",
                "source_device_name": None,
            }
    ]
