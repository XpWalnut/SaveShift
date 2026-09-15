import json
from pathlib import Path

import pytest

from app.steam.host_session_store import (
    SteamHostSessionCheckpoint,
    SteamHostSessionStore,
)


GROUP_ID = "87654321-4321-4678-9234-567812345678"
PROJECT_ID = "12345678-1234-4678-9234-567812345678"


def test_host_session_checkpoint_round_trips_and_removes_atomically(
    tmp_path: Path,
) -> None:
    store = SteamHostSessionStore(tmp_path / "sessions")
    checkpoint = SteamHostSessionCheckpoint.create(
        group_id=GROUP_ID,
        project_uuid=PROJECT_ID,
        parent_descriptor_hash="a" * 64,
        host_display_name="Jake",
    )

    store.save(checkpoint)

    assert store.load_all() == {PROJECT_ID: checkpoint}
    assert list((tmp_path / "sessions").glob("*.tmp")) == []
    store.remove(PROJECT_ID)
    assert store.load_all() == {}


def test_host_session_checkpoint_rejects_tampered_project_coordinate(
    tmp_path: Path,
) -> None:
    store = SteamHostSessionStore(tmp_path / "sessions")
    checkpoint = SteamHostSessionCheckpoint.create(
        group_id=GROUP_ID,
        project_uuid=PROJECT_ID,
        parent_descriptor_hash="",
        host_display_name="Jake",
    )
    store.save(checkpoint)
    path = next((tmp_path / "sessions").glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    value["project_uuid"] = "aaaaaaaa-1234-4678-9234-567812345678"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="host checkpoint is invalid"):
        store.load_all()
