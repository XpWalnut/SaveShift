from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database.database import Base
from app.database.migrations import runner
from app.database.migrations import (
    CURRENT_SCHEMA_VERSION,
    DatabaseMigrationError,
    DatabaseTooNewError,
    UnknownDatabaseSchemaError,
    initialize_database,
)


def _initialize(database_path: Path, backup_directory: Path):
    local_engine = create_engine(f"sqlite:///{database_path}")
    result = initialize_database(
        engine=local_engine,
        metadata=Base.metadata,
        database_path=database_path,
        backup_directory=backup_directory,
    )
    return local_engine, result


def _schema_version(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _create_legacy_v1_database(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE installed_games (
                id INTEGER PRIMARY KEY,
                game_id VARCHAR NOT NULL,
                display_name VARCHAR NOT NULL,
                save_path VARCHAR NOT NULL,
                enabled BOOLEAN NOT NULL
            );

            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                installed_game_id INTEGER NOT NULL
                    REFERENCES installed_games(id),
                name VARCHAR NOT NULL,
                local_path VARCHAR NOT NULL,
                uuid VARCHAR(36) NOT NULL UNIQUE
            );

            CREATE TABLE project_versions (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                version_number INTEGER NOT NULL,
                created_at_utc DATETIME NOT NULL,
                created_by VARCHAR(100) NOT NULL,
                source_type VARCHAR(25) NOT NULL,
                package_path TEXT,
                backup_path TEXT,
                package_checksum VARCHAR(64),
                parent_version_id INTEGER REFERENCES project_versions(id),
                lineage_name VARCHAR(100) NOT NULL,
                notes TEXT
            );

            INSERT INTO installed_games (
                id, game_id, display_name, save_path, enabled
            ) VALUES (1, 'valheim', 'Valheim', 'C:/Saves', 1);

            INSERT INTO projects (
                id, installed_game_id, name, local_path, uuid
            ) VALUES (
                1,
                1,
                'Migration World',
                'C:/Saves/Migration World',
                '4aa8f9ea-f387-4f53-844f-63e9771b5c39'
            );

            INSERT INTO project_versions (
                id,
                project_id,
                version_number,
                created_at_utc,
                created_by,
                source_type,
                lineage_name,
                notes
            ) VALUES (
                1,
                1,
                1,
                '2026-07-10 12:00:00',
                'Alice',
                'HOSTED',
                'main',
                'Legacy history remains intact.'
            );
            """
        )


def test_fresh_database_is_created_at_current_schema_version(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "fresh.sqlite3"
    backup_directory = tmp_path / "backups"

    local_engine, result = _initialize(database_path, backup_directory)

    assert result.fresh_database is True
    assert result.previous_version == 0
    assert result.current_version == CURRENT_SCHEMA_VERSION
    assert result.backup_path is None
    assert _schema_version(database_path) == CURRENT_SCHEMA_VERSION
    assert {
        "installed_games",
        "projects",
        "project_versions",
    }.issubset(inspect(local_engine).get_table_names())
    assert not backup_directory.exists()
    local_engine.dispose()


def test_legacy_pre_versioned_database_is_backed_up_and_migrated(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    backup_directory = tmp_path / "backups"
    _create_legacy_v1_database(database_path)

    local_engine, result = _initialize(database_path, backup_directory)

    assert result.previous_version == 1
    assert result.current_version == CURRENT_SCHEMA_VERSION
    assert result.backup_path is not None
    assert result.backup_path.is_file()
    assert _schema_version(database_path) == CURRENT_SCHEMA_VERSION
    assert "restored_from_version_id" in {
        column["name"]
        for column in inspect(local_engine).get_columns("project_versions")
    }

    with local_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT created_by, notes, restored_from_version_id "
                "FROM project_versions WHERE id = 1"
            )
        ).one()

    assert row == (
        "Alice",
        "Legacy history remains intact.",
        None,
    )
    assert _schema_version(result.backup_path) == 0

    with sqlite3.connect(result.backup_path) as backup:
        backup_columns = {
            row[1]
            for row in backup.execute("PRAGMA table_info(project_versions)")
        }

    assert "restored_from_version_id" not in backup_columns
    local_engine.dispose()


def test_unversioned_current_database_is_adopted_without_backup(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "current-unversioned.sqlite3"
    backup_directory = tmp_path / "backups"
    local_engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(bind=local_engine)

    with local_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO installed_games "
                "(id, game_id, display_name, save_path, enabled) "
                "VALUES (1, 'valheim', 'Valheim', 'C:/Saves', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, installed_game_id, name, local_path, uuid) VALUES "
                "(1, 1, 'Published Alpha World', "
                "'C:/Saves/Published Alpha World', "
                "'d3161a4a-a195-4395-9371-dd81b5f59bdf')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO project_versions "
                "(id, project_id, version_number, created_at_utc, "
                "created_by, source_type, lineage_name, notes) VALUES "
                "(1, 1, 3, '2026-07-13 12:00:00', 'Bob', 'IMPORTED', "
                "'main', 'Published alpha history remains intact.')"
            )
        )

    local_engine.dispose()

    local_engine, result = _initialize(database_path, backup_directory)

    assert result.previous_version == 0
    assert result.current_version == CURRENT_SCHEMA_VERSION
    assert result.backup_path is None
    assert _schema_version(database_path) == CURRENT_SCHEMA_VERSION
    assert not backup_directory.exists()

    with local_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT version_number, created_by, notes "
                "FROM project_versions WHERE id = 1"
            )
        ).one()

    assert row == (
        3,
        "Bob",
        "Published alpha history remains intact.",
    )
    local_engine.dispose()


def test_current_database_initialization_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "current.sqlite3"
    backup_directory = tmp_path / "backups"
    local_engine, _ = _initialize(database_path, backup_directory)
    local_engine.dispose()

    local_engine, result = _initialize(database_path, backup_directory)

    assert result.previous_version == CURRENT_SCHEMA_VERSION
    assert result.current_version == CURRENT_SCHEMA_VERSION
    assert result.backup_path is None
    local_engine.dispose()


def test_database_from_newer_application_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "future.sqlite3"
    backup_directory = tmp_path / "backups"
    local_engine, _ = _initialize(database_path, backup_directory)

    with local_engine.begin() as connection:
        connection.execute(
            text(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION + 1}")
        )

    with pytest.raises(DatabaseTooNewError, match="newer version"):
        initialize_database(
            engine=local_engine,
            metadata=Base.metadata,
            database_path=database_path,
            backup_directory=backup_directory,
        )

    local_engine.dispose()


def test_incomplete_database_is_rejected_without_modification(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "incomplete.sqlite3"
    backup_directory = tmp_path / "backups"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY)"
        )

    local_engine = create_engine(f"sqlite:///{database_path}")

    with pytest.raises(
        UnknownDatabaseSchemaError,
        match="Missing tables",
    ):
        initialize_database(
            engine=local_engine,
            metadata=Base.metadata,
            database_path=database_path,
            backup_directory=backup_directory,
        )

    assert inspect(local_engine).get_table_names() == ["projects"]
    assert not backup_directory.exists()
    local_engine.dispose()


def test_failed_migration_rolls_back_and_keeps_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "failed.sqlite3"
    backup_directory = tmp_path / "backups"
    _create_legacy_v1_database(database_path)
    local_engine = create_engine(f"sqlite:///{database_path}")

    def fail_after_schema_change(connection) -> None:
        connection.execute(
            text(
                "ALTER TABLE project_versions "
                "ADD COLUMN restored_from_version_id INTEGER"
            )
        )
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(
        runner,
        "MIGRATIONS",
        (
            runner.Migration(
                target_version=CURRENT_SCHEMA_VERSION,
                name="simulated failure",
                apply=fail_after_schema_change,
            ),
        ),
    )

    with pytest.raises(DatabaseMigrationError, match="restored automatically"):
        initialize_database(
            engine=local_engine,
            metadata=Base.metadata,
            database_path=database_path,
            backup_directory=backup_directory,
        )

    columns = {
        column["name"]
        for column in inspect(local_engine).get_columns("project_versions")
    }
    backups = list(backup_directory.glob("*.sqlite3"))

    assert "restored_from_version_id" not in columns
    assert _schema_version(database_path) == 0
    assert len(backups) == 1
    assert _schema_version(backups[0]) == 0
    local_engine.dispose()


def test_backup_failure_prevents_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "backup-failure.sqlite3"
    backup_directory = tmp_path / "backups"
    _create_legacy_v1_database(database_path)
    local_engine = create_engine(f"sqlite:///{database_path}")

    def fail_backup(_source_path: Path, _destination_path: Path) -> None:
        raise OSError("simulated backup failure")

    monkeypatch.setattr(runner, "_copy_sqlite_database", fail_backup)

    with pytest.raises(
        DatabaseMigrationError,
        match="no migration was attempted",
    ):
        initialize_database(
            engine=local_engine,
            metadata=Base.metadata,
            database_path=database_path,
            backup_directory=backup_directory,
        )

    columns = {
        column["name"]
        for column in inspect(local_engine).get_columns("project_versions")
    }

    assert "restored_from_version_id" not in columns
    assert _schema_version(database_path) == 0
    assert list(backup_directory.iterdir()) == []
    local_engine.dispose()


def test_invalid_migration_result_restores_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "invalid-result.sqlite3"
    backup_directory = tmp_path / "backups"
    _create_legacy_v1_database(database_path)
    local_engine = create_engine(f"sqlite:///{database_path}")

    monkeypatch.setattr(
        runner,
        "MIGRATIONS",
        (
            runner.Migration(
                target_version=CURRENT_SCHEMA_VERSION,
                name="invalid no-op migration",
                apply=lambda _connection: None,
            ),
        ),
    )

    with pytest.raises(DatabaseMigrationError, match="restored automatically"):
        initialize_database(
            engine=local_engine,
            metadata=Base.metadata,
            database_path=database_path,
            backup_directory=backup_directory,
        )

    columns = {
        column["name"]
        for column in inspect(local_engine).get_columns("project_versions")
    }
    backups = list(backup_directory.glob("*.sqlite3"))

    assert "restored_from_version_id" not in columns
    assert _schema_version(database_path) == 0
    assert len(backups) == 1
    assert _schema_version(backups[0]) == 0
    local_engine.dispose()
