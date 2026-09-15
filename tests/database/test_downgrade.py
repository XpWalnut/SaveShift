from pathlib import Path
import sqlite3

import pytest

from app.database.migrations.downgrade import (
    DatabaseDowngradeError,
    downgrade_database_to_develop,
)


def _schema_four_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE installed_games (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                installed_game_id INTEGER NOT NULL REFERENCES installed_games(id),
                name TEXT NOT NULL,
                coordination_group_id VARCHAR(36)
            );
            CREATE INDEX ix_projects_coordination_group_id
                ON projects (coordination_group_id);
            INSERT INTO projects (
                id, installed_game_id, name, coordination_group_id
            ) VALUES (1, 99, 'Mistwalkers', 'group-one');
            PRAGMA user_version = 4;
            """
        )


def _version(path: Path) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def test_downgrade_backs_up_and_removes_only_schema_four_fields(
    tmp_path: Path,
) -> None:
    database = tmp_path / "saveshift.sqlite3"
    backups = tmp_path / "backups"
    _schema_four_database(database)

    result = downgrade_database_to_develop(database, backups)

    assert result.changed
    assert result.backup_path is not None
    assert _version(database) == 3
    assert _version(result.backup_path) == 4
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(projects)")
        }
        row = connection.execute(
            "SELECT id, installed_game_id, name FROM projects"
        ).fetchone()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert "coordination_group_id" not in columns
    assert row == (1, 99, "Mistwalkers")
    assert violations == [("projects", 1, "installed_games", 0)]


def test_downgrade_is_safe_to_rerun_on_schema_three(tmp_path: Path) -> None:
    database = tmp_path / "saveshift.sqlite3"
    backups = tmp_path / "backups"
    _schema_four_database(database)
    downgrade_database_to_develop(database, backups)

    result = downgrade_database_to_develop(database, backups)

    assert not result.changed
    assert result.backup_path is None
    assert len(list(backups.iterdir())) == 1


def test_downgrade_refuses_unknown_schema_without_backup(tmp_path: Path) -> None:
    database = tmp_path / "saveshift.sqlite3"
    backups = tmp_path / "backups"
    _schema_four_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 5")

    with pytest.raises(DatabaseDowngradeError, match="only supports"):
        downgrade_database_to_develop(database, backups)

    assert _version(database) == 5
    assert not backups.exists()
