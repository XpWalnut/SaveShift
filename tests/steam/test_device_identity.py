import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.steam.device_identity import SteamDeviceIdentityStore, _decode


class MemoryProtector:
    def protect(self, value: str) -> str:
        return f"protected:{value}"

    def unprotect(self, value: str) -> str:
        assert value.startswith("protected:")
        return value.removeprefix("protected:")


def test_device_identity_is_stable_and_private_keys_are_protected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "identity.json"
    store = SteamDeviceIdentityStore(path, protector=MemoryProtector())

    created = store.load_or_create("76561198000000001")
    loaded = store.load_or_create("76561198000000001")
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert loaded.device_id == created.device_id
    assert loaded.signing_public_key == created.signing_public_key
    assert loaded.agreement_public_key == created.agreement_public_key
    assert stored["signing_key_protected"].startswith("protected:")
    assert stored["agreement_key_protected"].startswith("protected:")
    assert "private" not in json.dumps(stored).lower().replace("_key_protected", "")


def test_device_identity_signs_and_derives_pairwise_secret(tmp_path: Path) -> None:
    first = SteamDeviceIdentityStore(
        tmp_path / "first.json", protector=MemoryProtector()
    ).load_or_create("76561198000000001")
    second = SteamDeviceIdentityStore(
        tmp_path / "second.json", protector=MemoryProtector()
    ).load_or_create("76561198000000002")
    payload = b"Save Shift membership certificate"
    signature = first.sign(payload)

    Ed25519PublicKey.from_public_bytes(_decode(first.signing_public_key)).verify(
        _decode(signature), payload
    )
    assert first.shared_secret(second.agreement_public_key) == second.shared_secret(
        first.agreement_public_key
    )


def test_device_identity_cannot_be_reused_by_another_steam_account(
    tmp_path: Path,
) -> None:
    store = SteamDeviceIdentityStore(
        tmp_path / "identity.json", protector=MemoryProtector()
    )
    store.load_or_create("76561198000000001")

    with pytest.raises(ValueError, match="different Steam account"):
        store.load_or_create("76561198000000002")
