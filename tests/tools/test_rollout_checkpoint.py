import json
from pathlib import Path
import sqlite3

import pytest

from tools.rollout_checkpoint import (
    RolloutCheckpointError,
    create_checkpoint,
    restore_checkpoint,
)


def _database(path: Path, version: int, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES (?)", (value,))
        connection.execute(f"PRAGMA user_version = {version}")
        connection.commit()
    finally:
        connection.close()


def _marker(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("SELECT value FROM marker").fetchone()[0])
    finally:
        connection.close()


def test_checkpoint_restores_exact_database_and_settings(tmp_path: Path) -> None:
    data = tmp_path / "data"
    backups = tmp_path / "backups"
    database = data / "saveshift.sqlite3"
    settings = data / "settings.json"
    _database(database, 3, "before")
    settings.write_text('{"coordination_enabled": false}\n', encoding="utf-8")
    checkpoint = create_checkpoint(data, backups, label="pilot")

    database.unlink()
    _database(database, 4, "after")
    settings.write_text('{"coordination_enabled": true}\n', encoding="utf-8")

    safety = restore_checkpoint(checkpoint, data, backups)

    assert _marker(database) == "before"
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        connection.close()
    assert json.loads(settings.read_text(encoding="utf-8")) == {
        "coordination_enabled": False
    }
    assert (safety / "checkpoint.json").is_file()
    assert _marker(safety / "saveshift.sqlite3") == "after"


def test_tampered_checkpoint_is_rejected_before_current_state_changes(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    backups = tmp_path / "backups"
    database = data / "saveshift.sqlite3"
    _database(database, 3, "current")
    checkpoint = create_checkpoint(data, backups)
    (checkpoint / "saveshift.sqlite3").write_bytes(b"tampered")

    with pytest.raises(RolloutCheckpointError):
        restore_checkpoint(checkpoint, data, backups)

    assert _marker(database) == "current"
