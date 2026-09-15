import json
from pathlib import Path

import pytest

from app.steam.administrator_recovery import SteamAdministratorRecoveryService
from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from tests.steam.test_device_identity import MemoryProtector


def _group(tmp_path: Path):
    store = SteamDeviceIdentityStore(
        tmp_path / "identity.json",
        protector=MemoryProtector(),
    )
    identity = store.load_or_create("76561198000000001")
    manifest, group_key = SteamGroupManifest.create("Family Worlds", identity)
    manifest = manifest.set_member_package_index(
        device_id=identity.device_id,
        workshop_item_id="3797671910",
        administrator=identity,
    )
    return identity, manifest, group_key


def test_password_encrypted_recovery_kit_restores_administrator_identity(
    tmp_path: Path,
) -> None:
    identity, manifest, group_key = _group(tmp_path)
    path = tmp_path / "family.ssrecovery"

    SteamAdministratorRecoveryService.export(
        path,
        password="correct horse battery staple",
        identity=identity,
        manifest=manifest,
        manifest_item_id="3797671909",
        package_index_item_id="3797671910",
    )
    recovered = SteamAdministratorRecoveryService.import_kit(
        path,
        password="correct horse battery staple",
        signed_in_steam_id=identity.steam_id,
    )

    assert recovered.manifest == manifest
    assert recovered.manifest_item_id == "3797671909"
    assert recovered.package_index_item_id == "3797671910"
    assert recovered.identity.device_id == identity.device_id
    assert recovered.identity.signing_public_key == identity.signing_public_key
    assert recovered.manifest.group_key_for(recovered.identity) == group_key
    document = json.loads(path.read_text(encoding="utf-8"))
    serialized = path.read_text(encoding="utf-8")
    assert "signing_private_key" not in serialized
    assert "agreement_private_key" not in serialized
    assert document["cipher"]["name"] == "AES-256-GCM"


def test_recovery_rejects_wrong_password_tampering_and_wrong_steam_account(
    tmp_path: Path,
) -> None:
    identity, manifest, _group_key = _group(tmp_path)
    path = tmp_path / "family.ssrecovery"
    SteamAdministratorRecoveryService.export(
        path,
        password="correct horse battery staple",
        identity=identity,
        manifest=manifest,
        manifest_item_id="3797671909",
        package_index_item_id="3797671910",
    )

    with pytest.raises(ValueError, match="password is incorrect"):
        SteamAdministratorRecoveryService.import_kit(
            path,
            password="this password is wrong",
            signed_in_steam_id=identity.steam_id,
        )
    with pytest.raises(ValueError, match="different Steam account"):
        SteamAdministratorRecoveryService.import_kit(
            path,
            password="correct horse battery staple",
            signed_in_steam_id="76561198000000002",
        )

    document = json.loads(path.read_text(encoding="utf-8"))
    document["group_id"] = "12345678-1234-4678-9234-567812345678"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="password is incorrect|modified"):
        SteamAdministratorRecoveryService.import_kit(
            path,
            password="correct horse battery staple",
            signed_in_steam_id=identity.steam_id,
        )


def test_identity_restore_refuses_silent_replacement(tmp_path: Path) -> None:
    recovered_identity, _manifest, _key = _group(tmp_path / "source")
    target = SteamDeviceIdentityStore(
        tmp_path / "target.json",
        protector=MemoryProtector(),
    )
    target.load_or_create(recovered_identity.steam_id)

    with pytest.raises(ValueError, match="different Save Shift Steam identity"):
        target.restore(recovered_identity)

    target.restore(recovered_identity, overwrite=True)
    restored = target.load_or_create(recovered_identity.steam_id)
    assert restored.device_id == recovered_identity.device_id
    assert restored.signing_public_key == recovered_identity.signing_public_key


def test_recovery_rejects_malformed_encryption_material(tmp_path: Path) -> None:
    identity, manifest, _group_key = _group(tmp_path)
    path = tmp_path / "family.ssrecovery"
    SteamAdministratorRecoveryService.export(
        path,
        password="correct horse battery staple",
        identity=identity,
        manifest=manifest,
        manifest_item_id="3797671909",
        package_index_item_id="3797671910",
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["kdf"]["salt"] = "%%%"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="recovery kit is invalid"):
        SteamAdministratorRecoveryService.import_kit(
            path,
            password="correct horse battery staple",
            signed_in_steam_id=identity.steam_id,
        )
