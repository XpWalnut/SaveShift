import json
from pathlib import Path

import pytest

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.manifest_cache import SteamGroupManifestCache
from tests.steam.test_device_identity import MemoryProtector


def _manifest(tmp_path: Path) -> SteamGroupManifest:
    identity = SteamDeviceIdentityStore(
        tmp_path / "identity.json",
        protector=MemoryProtector(),
    ).load_or_create("76561198000000001")
    return SteamGroupManifest.create("Family Worlds", identity)[0]


def test_verified_manifest_cache_round_trips_atomically(tmp_path: Path) -> None:
    cache = SteamGroupManifestCache(tmp_path / "cache")
    manifest = _manifest(tmp_path)

    saved = cache.save("3797671909", manifest)
    restored = cache.load(
        manifest.group_id,
        expected_manifest_item_id="3797671909",
    )

    assert restored == saved
    assert list((tmp_path / "cache").glob("*.tmp")) == []


def test_cache_rejects_tampering_and_wrong_workshop_coordinate(
    tmp_path: Path,
) -> None:
    cache = SteamGroupManifestCache(tmp_path / "cache")
    manifest = _manifest(tmp_path)
    cache.save("3797671909", manifest)

    with pytest.raises(ValueError, match="cached Steam group manifest"):
        cache.load(
            manifest.group_id,
            expected_manifest_item_id="3797671910",
        )

    path = next((tmp_path / "cache").glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    value["manifest"]["name"] = "Impostor"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="cached Steam group manifest"):
        cache.load(manifest.group_id)


def test_missing_cache_returns_none(tmp_path: Path) -> None:
    cache = SteamGroupManifestCache(tmp_path / "cache")
    assert cache.load("12345678-1234-4678-9234-567812345678") is None
