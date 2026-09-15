"""Create and restore verified Save Shift rollout checkpoints."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.version import APP_VERSION


class RolloutCheckpointError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_info(path: Path) -> tuple[int, str]:
    if not path.is_file():
        raise RolloutCheckpointError(f"Database not found: {path}")
    connection = None
    try:
        connection = sqlite3.connect(path)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    except sqlite3.Error as error:
        raise RolloutCheckpointError(f"Could not read database: {error}") from error
    finally:
        if connection is not None:
            connection.close()
    if integrity != "ok":
        raise RolloutCheckpointError("The database failed SQLite's integrity check.")
    return version, _sha256(path)


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def create_checkpoint(
    data_directory: Path,
    backup_root: Path,
    *,
    label: str = "pre-update",
) -> Path:
    data_directory = data_directory.expanduser().resolve()
    backup_root = backup_root.expanduser().resolve()
    database = data_directory / "saveshift.sqlite3"
    settings = data_directory / "settings.json"
    _database_info(database)
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-._")
    if not safe_label:
        safe_label = "checkpoint"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_root / f"{timestamp}-{safe_label}"
    try:
        destination.mkdir(parents=True, exist_ok=False)
        checkpoint_database = destination / "saveshift.sqlite3"
        _sqlite_backup(database, checkpoint_database)
        database_version, database_hash = _database_info(checkpoint_database)
        settings_hash = None
        if settings.is_file():
            shutil.copy2(settings, destination / "settings.json")
            settings_hash = _sha256(destination / "settings.json")
        manifest = {
            "format_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "created_by_app_version": APP_VERSION,
            "database_user_version": database_version,
            "database_sha256": database_hash,
            "settings_present": settings_hash is not None,
            "settings_sha256": settings_hash,
        }
        (destination / "checkpoint.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination


def _validate_checkpoint(checkpoint: Path) -> dict[str, object]:
    checkpoint = checkpoint.expanduser().resolve()
    manifest_path = checkpoint / "checkpoint.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RolloutCheckpointError("The checkpoint manifest is unreadable.") from error
    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        raise RolloutCheckpointError("The checkpoint format is unsupported.")
    database = checkpoint / "saveshift.sqlite3"
    version, database_hash = _database_info(database)
    if version != manifest.get("database_user_version"):
        raise RolloutCheckpointError("The checkpoint database schema does not match its manifest.")
    if database_hash != manifest.get("database_sha256"):
        raise RolloutCheckpointError("The checkpoint database checksum does not match.")
    settings = checkpoint / "settings.json"
    if bool(manifest.get("settings_present")) != settings.is_file():
        raise RolloutCheckpointError("The checkpoint settings state does not match its manifest.")
    if settings.is_file() and _sha256(settings) != manifest.get("settings_sha256"):
        raise RolloutCheckpointError("The checkpoint settings checksum does not match.")
    return manifest


def restore_checkpoint(
    checkpoint: Path,
    data_directory: Path,
    backup_root: Path,
) -> Path:
    checkpoint = checkpoint.expanduser().resolve()
    data_directory = data_directory.expanduser().resolve()
    backup_root = backup_root.expanduser().resolve()
    manifest = _validate_checkpoint(checkpoint)
    safety = create_checkpoint(
        data_directory,
        backup_root / "pre-rollback",
        label="before-rollback",
    )
    data_directory.mkdir(parents=True, exist_ok=True)
    temporary_database = data_directory / "saveshift.rollback.tmp.sqlite3"
    try:
        temporary_database.unlink(missing_ok=True)
        _sqlite_backup(checkpoint / "saveshift.sqlite3", temporary_database)
        version, digest = _database_info(temporary_database)
        if version != manifest["database_user_version"] or digest != manifest["database_sha256"]:
            raise RolloutCheckpointError("The staged rollback database did not verify.")
        temporary_database.replace(data_directory / "saveshift.sqlite3")
        destination_settings = data_directory / "settings.json"
        if bool(manifest["settings_present"]):
            temporary_settings = data_directory / "settings.rollback.tmp.json"
            shutil.copy2(checkpoint / "settings.json", temporary_settings)
            temporary_settings.replace(destination_settings)
        else:
            destination_settings.unlink(missing_ok=True)
    except Exception as error:
        temporary_database.unlink(missing_ok=True)
        raise RolloutCheckpointError(
            "Rollback failed. The state from immediately before the attempt is "
            f"preserved at {safety}."
        ) from error
    return safety


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--data-directory", required=True, type=Path)
    create.add_argument("--backup-root", required=True, type=Path)
    create.add_argument("--label", default="pre-update")
    restore = subparsers.add_parser("restore")
    restore.add_argument("--checkpoint", required=True, type=Path)
    restore.add_argument("--data-directory", required=True, type=Path)
    restore.add_argument("--backup-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_checkpoint(
                args.data_directory,
                args.backup_root,
                label=args.label,
            )
            print(f"Verified rollout checkpoint: {result}")
        else:
            safety = restore_checkpoint(
                args.checkpoint,
                args.data_directory,
                args.backup_root,
            )
            print("Checkpoint restored successfully.")
            print(f"Pre-rollback safety checkpoint: {safety}")
    except RolloutCheckpointError as error:
        print(f"Checkpoint operation aborted: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
