from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from sqlalchemy import Connection, Engine, MetaData, inspect, text


CURRENT_SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1

_APPLICATION_TABLES = {
    "installed_games",
    "projects",
    "project_versions",
}

_BASELINE_COLUMNS = {
    "installed_games": {
        "id",
        "game_id",
        "display_name",
        "save_path",
        "enabled",
    },
    "projects": {
        "id",
        "installed_game_id",
        "name",
        "local_path",
        "uuid",
    },
    "project_versions": {
        "id",
        "project_id",
        "version_number",
        "created_at_utc",
        "created_by",
        "source_type",
        "package_path",
        "backup_path",
        "package_checksum",
        "parent_version_id",
        "lineage_name",
        "notes",
    },
}


class DatabaseMigrationError(RuntimeError):
    """Base error raised when Save Shift cannot safely prepare its database."""


class DatabaseTooNewError(DatabaseMigrationError):
    """The database belongs to a newer Save Shift schema."""


class UnknownDatabaseSchemaError(DatabaseMigrationError):
    """An unversioned database does not match a supported alpha schema."""


@dataclass(frozen=True)
class Migration:
    target_version: int
    name: str
    apply: Callable[[Connection], None]


@dataclass(frozen=True)
class MigrationResult:
    previous_version: int
    current_version: int
    backup_path: Path | None = None
    fresh_database: bool = False


def _add_restored_from_version_id(connection: Connection) -> None:
    connection.execute(
        text(
            """
            ALTER TABLE project_versions
            ADD COLUMN restored_from_version_id INTEGER
            REFERENCES project_versions(id)
            """
        )
    )


MIGRATIONS = (
    Migration(
        target_version=2,
        name="add restored version lineage",
        apply=_add_restored_from_version_id,
    ),
)


def initialize_database(
    *,
    engine: Engine,
    metadata: MetaData,
    database_path: Path,
    backup_directory: Path,
) -> MigrationResult:
    """Create or upgrade a Save Shift database to the current schema."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    application_tables = table_names & _APPLICATION_TABLES

    if not application_tables:
        metadata.create_all(bind=engine)
        _set_schema_version(engine, CURRENT_SCHEMA_VERSION)
        return MigrationResult(
            previous_version=0,
            current_version=CURRENT_SCHEMA_VERSION,
            fresh_database=True,
        )

    if application_tables != _APPLICATION_TABLES:
        missing = ", ".join(sorted(_APPLICATION_TABLES - application_tables))
        raise UnknownDatabaseSchemaError(
            "The Save Shift database is incomplete and cannot be upgraded "
            f"safely. Missing tables: {missing}."
        )

    stored_version = _get_schema_version(engine)

    if stored_version > CURRENT_SCHEMA_VERSION:
        raise DatabaseTooNewError(
            "This database was created by a newer version of Save Shift "
            f"(schema {stored_version}; supported through "
            f"{CURRENT_SCHEMA_VERSION}). Install the newer application "
            "version to open it."
        )

    if stored_version == 0:
        detected_version = _detect_unversioned_schema(engine)

        if detected_version == CURRENT_SCHEMA_VERSION:
            _set_schema_version(engine, CURRENT_SCHEMA_VERSION)
            metadata.create_all(bind=engine)
            return MigrationResult(
                previous_version=0,
                current_version=CURRENT_SCHEMA_VERSION,
            )

        stored_version = detected_version

    _validate_schema(engine, stored_version)
    pending = [
        migration
        for migration in MIGRATIONS
        if migration.target_version > stored_version
    ]

    if not pending:
        metadata.create_all(bind=engine)
        return MigrationResult(
            previous_version=stored_version,
            current_version=stored_version,
        )

    backup_path = _backup_database(
        database_path=database_path,
        backup_directory=backup_directory,
        previous_version=stored_version,
        target_version=CURRENT_SCHEMA_VERSION,
    )

    try:
        with engine.begin() as connection:
            for migration in pending:
                migration.apply(connection)
                connection.execute(
                    text(f"PRAGMA user_version = {migration.target_version}")
                )

        _validate_schema(engine, CURRENT_SCHEMA_VERSION)
        metadata.create_all(bind=engine)
    except Exception as error:
        engine.dispose()

        try:
            _copy_sqlite_database(backup_path, database_path)
        except Exception as restore_error:
            raise DatabaseMigrationError(
                "Save Shift could not upgrade its database or restore it "
                "automatically. Do not continue using the database. The "
                f"untouched backup is available at {backup_path}."
            ) from restore_error

        raise DatabaseMigrationError(
            "Save Shift could not upgrade its database, so the original was "
            f"restored automatically. Its backup remains at {backup_path}."
        ) from error

    return MigrationResult(
        previous_version=stored_version,
        current_version=CURRENT_SCHEMA_VERSION,
        backup_path=backup_path,
    )


def _get_schema_version(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("PRAGMA user_version")).scalar_one())


def _set_schema_version(engine: Engine, version: int) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"PRAGMA user_version = {version}"))


def _detect_unversioned_schema(engine: Engine) -> int:
    _validate_baseline_columns(engine)
    columns = _column_names(engine, "project_versions")

    if "restored_from_version_id" in columns:
        return CURRENT_SCHEMA_VERSION

    return LEGACY_SCHEMA_VERSION


def _validate_schema(engine: Engine, version: int) -> None:
    if version < LEGACY_SCHEMA_VERSION:
        raise UnknownDatabaseSchemaError(
            f"Database schema version {version} is not supported."
        )

    _validate_baseline_columns(engine)
    columns = _column_names(engine, "project_versions")

    if version >= 2 and "restored_from_version_id" not in columns:
        raise UnknownDatabaseSchemaError(
            "The database schema version does not match its project history "
            "columns. Restore a database backup or reinstall the matching "
            "Save Shift version."
        )

    if version == 1 and "restored_from_version_id" in columns:
        raise UnknownDatabaseSchemaError(
            "The database reports schema version 1 but already contains "
            "version 2 project history columns."
        )


def _validate_baseline_columns(engine: Engine) -> None:
    for table_name, required_columns in _BASELINE_COLUMNS.items():
        columns = _column_names(engine, table_name)
        missing = required_columns - columns

        if missing:
            missing_names = ", ".join(sorted(missing))
            raise UnknownDatabaseSchemaError(
                f"The {table_name} table is missing required columns: "
                f"{missing_names}."
            )


def _column_names(engine: Engine, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in inspect(engine).get_columns(table_name)
    }


def _backup_database(
    *,
    database_path: Path,
    backup_directory: Path,
    previous_version: int,
    target_version: int,
) -> Path:
    resolved_database = database_path.resolve()

    if not resolved_database.is_file():
        raise DatabaseMigrationError(
            f"The database file could not be backed up: {resolved_database}."
        )

    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_directory / (
        f"{resolved_database.stem}.schema-v{previous_version}-to-v"
        f"{target_version}.{timestamp}{resolved_database.suffix}"
    )

    try:
        _copy_sqlite_database(resolved_database, backup_path)
    except Exception as error:
        backup_path.unlink(missing_ok=True)
        raise DatabaseMigrationError(
            "Save Shift could not back up the database, so no migration was "
            "attempted."
        ) from error

    return backup_path


def _copy_sqlite_database(source_path: Path, destination_path: Path) -> None:
    source = None
    destination = None

    try:
        source = sqlite3.connect(source_path)
        destination = sqlite3.connect(destination_path)
        source.backup(destination)
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
