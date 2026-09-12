from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path

import pytest

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from tests.steam.test_device_identity import MemoryProtector


def _identity(tmp_path: Path, name: str, steam_id: str):
    return SteamDeviceIdentityStore(
        tmp_path / f"{name}.json",
        protector=MemoryProtector(),
    ).load_or_create(steam_id)


def test_group_manifest_round_trips_and_opens_administrator_key(
    tmp_path: Path,
) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    group_key = os.urandom(32)
    manifest, returned_key = SteamGroupManifest.create(
        "Family Worlds",
        administrator,
        group_key=group_key,
        updated_at=datetime(2026, 9, 12, tzinfo=UTC),
    )

    restored = SteamGroupManifest.from_json(manifest.to_json())

    assert returned_key == group_key
    assert restored.name == "Family Worlds"
    assert restored.revision == 1
    assert restored.group_key_for(administrator) == group_key
    assert restored.verify()


def test_group_manifest_adds_member_with_device_specific_key(
    tmp_path: Path,
) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)

    updated = manifest.add_member(member, group_key, administrator)

    assert updated.revision == 2
    assert {item.device_id for item in updated.active_members} == {
        administrator.device_id,
        member.device_id,
    }
    assert updated.group_key_for(member) == group_key
    assert SteamGroupManifest.from_json(updated.to_json()) == updated


def test_revocation_rotates_key_and_removes_member_envelope(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)
    manifest = manifest.add_member(member, group_key, administrator)
    replacement_key = os.urandom(32)

    updated, returned_key = manifest.revoke_member(
        member.device_id,
        administrator,
        replacement_group_key=replacement_key,
    )

    assert returned_key == replacement_key
    assert updated.key_epoch == 2
    assert updated.revision == 3
    assert [item.device_id for item in updated.active_members] == [
        administrator.device_id
    ]
    assert updated.group_key_for(administrator) == replacement_key
    with pytest.raises(ValueError, match="not an active group member"):
        updated.group_key_for(member)


def test_manifest_rejects_modified_name_and_unknown_revocation(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    manifest, _ = SteamGroupManifest.create("Friends", administrator)
    changed_name = json.loads(manifest.to_json())
    changed_name["name"] = "Impostor group"

    with pytest.raises(ValueError, match="signature is invalid"):
        SteamGroupManifest.from_json(json.dumps(changed_name))

    unknown_revocation = replace(
        manifest,
        revoked_certificate_ids=("a7b69ccd-1143-4a31-a95f-96944bce064f",),
    )
    assert not unknown_revocation.verify()


def test_non_administrator_cannot_change_manifest(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    stranger = _identity(tmp_path, "stranger", "76561198000000003")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)

    with pytest.raises(ValueError, match="administrator"):
        manifest.add_member(member, group_key, stranger)
