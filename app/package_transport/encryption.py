import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.package_transport.errors import PackageEncryptionError


class PackageEncryption:
    """Streaming authenticated encryption for package transport payloads."""

    MAGIC = b"SSPKG-E1"
    NONCE_SIZE = 12
    TAG_SIZE = 16
    KEY_SIZE = 32
    CHUNK_SIZE = 1024 * 1024

    @classmethod
    def encrypt(
        cls,
        package_path: Path,
        encrypted_path: Path,
        key: bytes,
    ) -> Path:
        cls._validate_paths_and_key(package_path, encrypted_path, key)
        encrypted_path.parent.mkdir(parents=True, exist_ok=True)
        nonce = os.urandom(cls.NONCE_SIZE)
        encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
        ).encryptor()
        encryptor.authenticate_additional_data(cls.MAGIC)

        try:
            with package_path.open("rb") as source, encrypted_path.open("wb") as target:
                target.write(cls.MAGIC)
                target.write(nonce)

                for chunk in iter(lambda: source.read(cls.CHUNK_SIZE), b""):
                    target.write(encryptor.update(chunk))

                target.write(encryptor.finalize())
                target.write(encryptor.tag)
        except Exception:
            cls._remove_partial(encrypted_path)
            raise

        return encrypted_path

    @classmethod
    def decrypt(
        cls,
        encrypted_path: Path,
        package_path: Path,
        key: bytes,
    ) -> Path:
        cls._validate_paths_and_key(encrypted_path, package_path, key)
        minimum_size = len(cls.MAGIC) + cls.NONCE_SIZE + cls.TAG_SIZE

        if encrypted_path.stat().st_size < minimum_size:
            raise PackageEncryptionError(
                "The encrypted package is incomplete or invalid."
            )

        package_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with encrypted_path.open("rb") as source:
                magic = source.read(len(cls.MAGIC))

                if magic != cls.MAGIC:
                    raise PackageEncryptionError(
                        "The file is not an encrypted Save Shift package."
                    )

                nonce = source.read(cls.NONCE_SIZE)
                ciphertext_size = (
                    encrypted_path.stat().st_size
                    - len(cls.MAGIC)
                    - cls.NONCE_SIZE
                    - cls.TAG_SIZE
                )
                source.seek(-cls.TAG_SIZE, os.SEEK_END)
                tag = source.read(cls.TAG_SIZE)
                source.seek(len(cls.MAGIC) + cls.NONCE_SIZE)
                decryptor = Cipher(
                    algorithms.AES(key),
                    modes.GCM(nonce, tag),
                ).decryptor()
                decryptor.authenticate_additional_data(cls.MAGIC)

                with package_path.open("wb") as target:
                    remaining = ciphertext_size

                    while remaining > 0:
                        chunk = source.read(min(cls.CHUNK_SIZE, remaining))

                        if not chunk:
                            raise PackageEncryptionError(
                                "The encrypted package ended unexpectedly."
                            )

                        target.write(decryptor.update(chunk))
                        remaining -= len(chunk)

                    target.write(decryptor.finalize())
        except InvalidTag as error:
            cls._remove_partial(package_path)
            raise PackageEncryptionError(
                "The encrypted package could not be authenticated."
            ) from error
        except Exception:
            cls._remove_partial(package_path)
            raise

        return package_path

    @classmethod
    def _validate_paths_and_key(
        cls,
        source_path: Path,
        destination_path: Path,
        key: bytes,
    ) -> None:
        if not isinstance(key, bytes) or len(key) != cls.KEY_SIZE:
            raise PackageEncryptionError(
                "Package encryption requires a 256-bit key."
            )
        if not source_path.is_file():
            raise FileNotFoundError(f"Package payload does not exist: {source_path}")
        if source_path.resolve() == destination_path.resolve():
            raise PackageEncryptionError(
                "Encrypted input and output paths must be different."
            )

    @staticmethod
    def _remove_partial(path: Path) -> None:
        if path.is_file() or path.is_symlink():
            path.unlink()
