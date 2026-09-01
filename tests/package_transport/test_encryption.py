from pathlib import Path

import pytest

from app.package_transport.encryption import PackageEncryption
from app.package_transport.errors import PackageEncryptionError


def test_streaming_encryption_round_trip_preserves_package_bytes(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "world.sspkg"
    package_path.write_bytes(
        b"header" + bytes(range(256)) * 9000 + b"footer"
    )
    encrypted_path = tmp_path / "world.sspkg.enc"
    decrypted_path = tmp_path / "received.sspkg"
    key = bytes(range(32))

    PackageEncryption.encrypt(package_path, encrypted_path, key)
    PackageEncryption.decrypt(encrypted_path, decrypted_path, key)

    assert encrypted_path.read_bytes() != package_path.read_bytes()
    assert decrypted_path.read_bytes() == package_path.read_bytes()
    assert encrypted_path.stat().st_size == (
        package_path.stat().st_size
        + len(PackageEncryption.MAGIC)
        + PackageEncryption.NONCE_SIZE
        + PackageEncryption.TAG_SIZE
    )


def test_wrong_key_rejects_payload_and_removes_partial_output(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "world.sspkg"
    package_path.write_bytes(b"private save package")
    encrypted_path = tmp_path / "world.sspkg.enc"
    destination = tmp_path / "received.sspkg"
    PackageEncryption.encrypt(package_path, encrypted_path, bytes(range(32)))

    with pytest.raises(PackageEncryptionError, match="authenticated"):
        PackageEncryption.decrypt(encrypted_path, destination, b"x" * 32)

    assert not destination.exists()


def test_modified_ciphertext_is_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sspkg"
    source.write_bytes(b"important world state")
    encrypted = tmp_path / "source.sspkg.enc"
    PackageEncryption.encrypt(source, encrypted, b"k" * 32)
    payload = bytearray(encrypted.read_bytes())
    payload[len(PackageEncryption.MAGIC) + PackageEncryption.NONCE_SIZE] ^= 1
    encrypted.write_bytes(payload)

    with pytest.raises(PackageEncryptionError, match="authenticated"):
        PackageEncryption.decrypt(encrypted, tmp_path / "output.sspkg", b"k" * 32)


@pytest.mark.parametrize("key", [b"", b"short", b"x" * 31, b"x" * 33])
def test_encryption_rejects_non_256_bit_keys(
    tmp_path: Path,
    key: bytes,
) -> None:
    source = tmp_path / "source.sspkg"
    source.write_bytes(b"save")

    with pytest.raises(PackageEncryptionError, match="256-bit"):
        PackageEncryption.encrypt(source, tmp_path / "encrypted", key)


def test_decryption_rejects_unknown_file_format(tmp_path: Path) -> None:
    encrypted = tmp_path / "invalid.enc"
    encrypted.write_bytes(b"not-a-save-shift-encrypted-package" + b"x" * 32)

    with pytest.raises(PackageEncryptionError, match="not an encrypted"):
        PackageEncryption.decrypt(encrypted, tmp_path / "output", b"k" * 32)
