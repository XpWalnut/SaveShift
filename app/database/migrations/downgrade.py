from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3


DEVELOP_SCHEMA_VERSION = 3
SOURCE_SCHEMA_VERSION = 4
_GROUP_COLUMN = "coordination_group_id"
_GROUP_INDEX = "ix_projects_coordination_group_id"


class DatabaseDowngradeError(RuntimeError):
    """Raised when a database cannot be safely returned to develop schema 3."""


@dataclass(frozen=True)
class DatabaseDowngradeResult:
    previous_version: int
    current_version: int
    backup_path: Path | None
    changed: bool


def downgrade_database_to_develop(
    database_path: Path,
    backup_directory: Path,
) -> DatabaseDowngradeResult:
    """Remove only schema-4 project-group associations and preserve all saves."""
    database_path = database_path.expanduser().resolve()
    backup_directory = backup_directory.expanduser().resolve()
    if not database_path.is_file():
        raise DatabaseDowngradeError(
            f"The Save Shift database was not found: {database_path}"
        )

    with sqlite3.connect(database_path, timeout=5) as connection:
        previous_version = _schema_version(connection)
        if previous_version == DEVELOP_SCHEMA_VERSION:
            _validate_schema_three(connection)
            return DatabaseDowngradeResult(3, 3, None, False)
        if previous_version != SOURCE_SCHEMA_VERSION:
            raise DatabaseDowngradeError(
                "This tool only supports Save Shift schema 4 to schema 3; "
                f"the selected database reports schema {previous_version}."
            )
        _validate_schema_four(connection)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DatabaseDowngradeError(
                "The database failed SQLite's integrity check. It was not changed."
            )
        existing_foreign_key_violations = tuple(
            connection.execute("PRAGMA foreign_key_check").fetchall()
        )

    backup_path = _backup_database(database_path, backup_directory)
    try:
        with sqlite3.connect(database_path, timeout=5) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(f"DROP INDEX IF EXISTS {_GROUP_INDEX}")
            connection.execute(
                f"ALTER TABLE projects DROP COLUMN {_GROUP_COLUMN}"
            )
            connection.execute(f"PRAGMA user_version = {DEVELOP_SCHEMA_VERSION}")
            connection.commit()
            _validate_schema_three(connection)
            remaining_foreign_key_violations = tuple(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            )
            if remaining_foreign_key_violations != existing_foreign_key_violations:
                raise DatabaseDowngradeError(
                    "The downgrade changed the database's foreign-key check results."
                )
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise DatabaseDowngradeError(
                    "The downgraded database failed its integrity check."
                )
    except Exception as error:
        try:
            _copy_database(backup_path, database_path)
        except Exception as restore_error:
            raise DatabaseDowngradeError(
                "The downgrade failed and the automatic restore also failed. "
                f"Your untouched backup is at {backup_path}."
            ) from restore_error
        raise DatabaseDowngradeError(
            "The downgrade failed, so the original schema-4 database was "
            f"restored. Its backup remains at {backup_path}."
        ) from error

    return DatabaseDowngradeResult(
        previous_version=SOURCE_SCHEMA_VERSION,
        current_version=DEVELOP_SCHEMA_VERSION,
        backup_path=backup_path,
        changed=True,
    )


def _validate_schema_four(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "projects")
    if _GROUP_COLUMN not in columns:
        raise DatabaseDowngradeError(
            "The database reports schema 4 but has no project group association."
        )


def _validate_schema_three(connection: sqlite3.Connection) -> None:
    if _schema_version(connection) != DEVELOP_SCHEMA_VERSION:
        raise DatabaseDowngradeError("The database is not using schema 3.")
    if _GROUP_COLUMN in _columns(connection, "projects"):
        raise DatabaseDowngradeError(
            "The schema-4 project group association is still present."
        )
    indexes = {
        str(row[1]) for row in connection.execute("PRAGMA index_list(projects)")
    }
    if _GROUP_INDEX in indexes:
        raise DatabaseDowngradeError("The schema-4 project group index remains.")


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    if table_name not in {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }:
        raise DatabaseDowngradeError(
            f"The database is missing its {table_name} table."
        )
    return {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _backup_database(database_path: Path, backup_directory: Path) -> Path:
    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_directory / (
        f"{database_path.stem}.schema-v4-to-v3.{timestamp}{database_path.suffix}"
    )
    try:
        _copy_database(database_path, backup_path)
        with sqlite3.connect(backup_path) as backup:
            if _schema_version(backup) != SOURCE_SCHEMA_VERSION:
                raise DatabaseDowngradeError("The backup has the wrong schema version.")
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise DatabaseDowngradeError("The backup failed its integrity check.")
    except Exception as error:
        backup_path.unlink(missing_ok=True)
        raise DatabaseDowngradeError(
            "Save Shift could not create a verified backup. The database was not changed."
        ) from error
    return backup_path


def _copy_database(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
