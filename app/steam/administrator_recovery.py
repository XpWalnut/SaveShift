from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import binascii
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.steam.device_identity import SteamDeviceIdentity, _decode, _encode
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_security import _canonical_json


@dataclass(frozen=True)
class RecoveredSteamAdministrator:
    identity: SteamDeviceIdentity
    manifest: SteamGroupManifest
    manifest_item_id: str
    package_index_item_id: str
    group_name: str


class SteamAdministratorRecoveryService:
    """Exports the group administrator identity in a password-encrypted kit."""

    SCHEMA_VERSION = 1
    KIND = "saveshift-steam-administrator-recovery"
    KDF_N = 2**15
    KDF_R = 8
    KDF_P = 1

    @classmethod
    def export(
        cls,
        destination: Path,
        *,
        password: str,
        identity: SteamDeviceIdentity,
        manifest: SteamGroupManifest,
        manifest_item_id: str,
        package_index_item_id: str,
    ) -> Path:
        cls._password(password)
        cls._validate_administrator(identity, manifest)
        item_id = cls._item_id(manifest_item_id)
        package_index_id = cls._item_id(package_index_item_id)
        reference = next(
            (
                item
                for item in manifest.member_package_indexes
                if item.device_id == identity.device_id
            ),
            None,
        )
        if reference is None or reference.workshop_item_id != package_index_id:
            raise ValueError("The administrator package index does not match the manifest.")

        salt = os.urandom(16)
        nonce = os.urandom(12)
        header = {
            "schema_version": cls.SCHEMA_VERSION,
            "kind": cls.KIND,
            "group_id": manifest.group_id,
            "administrator_steam_id": identity.steam_id,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "kdf": {
                "name": "scrypt",
                "n": cls.KDF_N,
                "r": cls.KDF_R,
                "p": cls.KDF_P,
                "salt": cls._b64(salt),
            },
            "cipher": {"name": "AES-256-GCM", "nonce": cls._b64(nonce)},
        }
        payload = {
            "device_id": identity.device_id,
            "signing_private_key": _encode(
                identity.signing_key.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
            ),
            "agreement_private_key": _encode(
                identity.agreement_key.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
            ),
            "manifest_item_id": item_id,
            "package_index_item_id": package_index_id,
            "manifest": json.loads(manifest.to_json()),
        }
        ciphertext = AESGCM(cls._derive(password, salt)).encrypt(
            nonce,
            _canonical_json(payload),
            _canonical_json(header),
        )
        document = {**header, "ciphertext": cls._b64(ciphertext)}
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
        return destination

    @classmethod
    def import_kit(
        cls,
        source: Path,
        *,
        password: str,
        signed_in_steam_id: str,
    ) -> RecoveredSteamAdministrator:
        cls._password(password)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
            header = {key: document[key] for key in (
                "schema_version",
                "kind",
                "group_id",
                "administrator_steam_id",
                "created_at_utc",
                "kdf",
                "cipher",
            )}
            if header["schema_version"] != cls.SCHEMA_VERSION or header["kind"] != cls.KIND:
                raise ValueError("unsupported recovery format")
            if str(header["administrator_steam_id"]) != str(signed_in_steam_id):
                raise ValueError(
                    "This recovery kit belongs to a different Steam account."
                )
            kdf = header["kdf"]
            cipher = header["cipher"]
            if not isinstance(kdf, dict) or not isinstance(cipher, dict):
                raise ValueError("invalid recovery parameters")
            if (
                kdf.get("name") != "scrypt"
                or kdf.get("n") != cls.KDF_N
                or kdf.get("r") != cls.KDF_R
                or kdf.get("p") != cls.KDF_P
                or cipher.get("name") != "AES-256-GCM"
            ):
                raise ValueError("unsupported recovery encryption")
            salt = cls._unb64(kdf["salt"])
            nonce = cls._unb64(cipher["nonce"])
            ciphertext = cls._unb64(document["ciphertext"])
            if len(salt) != 16 or len(nonce) != 12 or len(ciphertext) < 16:
                raise ValueError("invalid recovery encryption parameters")
            plaintext = AESGCM(cls._derive(password, salt)).decrypt(
                nonce,
                ciphertext,
                _canonical_json(header),
            )
            payload = json.loads(plaintext)
            manifest = SteamGroupManifest.from_json(json.dumps(payload["manifest"]))
            identity = SteamDeviceIdentity(
                device_id=str(payload["device_id"]),
                steam_id=str(header["administrator_steam_id"]),
                signing_key=Ed25519PrivateKey.from_private_bytes(
                    _decode(str(payload["signing_private_key"]))
                ),
                agreement_key=X25519PrivateKey.from_private_bytes(
                    _decode(str(payload["agreement_private_key"]))
                ),
            )
            cls._validate_administrator(identity, manifest)
            if manifest.group_id != str(header["group_id"]):
                raise ValueError("The recovery manifest belongs to another group.")
            manifest_item_id = cls._item_id(payload["manifest_item_id"])
            package_index_item_id = cls._item_id(payload["package_index_item_id"])
        except InvalidTag as error:
            raise ValueError("The recovery password is incorrect or the kit was modified.") from error
        except (
            KeyError,
            TypeError,
            ValueError,
            binascii.Error,
            json.JSONDecodeError,
        ) as error:
            if isinstance(error, ValueError) and str(error).startswith("This recovery kit belongs"):
                raise
            raise ValueError("The administrator recovery kit is invalid.") from error
        return RecoveredSteamAdministrator(
            identity=identity,
            manifest=manifest,
            manifest_item_id=manifest_item_id,
            package_index_item_id=package_index_item_id,
            group_name=manifest.name,
        )

    @classmethod
    def _derive(cls, password: str, salt: bytes) -> bytes:
        return Scrypt(salt=salt, length=32, n=cls.KDF_N, r=cls.KDF_R, p=cls.KDF_P).derive(
            password.encode("utf-8")
        )

    @staticmethod
    def _validate_administrator(
        identity: SteamDeviceIdentity,
        manifest: SteamGroupManifest,
    ) -> None:
        if (
            not manifest.verify()
            or identity.steam_id != manifest.administrator_steam_id
            or identity.device_id != manifest.administrator_device_id
            or identity.signing_public_key
            != manifest.administrator_signing_public_key
        ):
            raise ValueError("The recovery identity is not this group's administrator.")
        manifest.group_key_for(identity)

    @staticmethod
    def _password(value: str) -> None:
        if len(value) < 12:
            raise ValueError("Recovery passwords must contain at least 12 characters.")

    @staticmethod
    def _item_id(value: object) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("A recovery Workshop item identifier is invalid.")
        return normalized

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(value: object) -> bytes:
        text = str(value)
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
