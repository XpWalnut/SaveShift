from dataclasses import dataclass
import base64
import json
from pathlib import Path
from typing import Protocol
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)

from app.core.config import AppConfig
from app.core.secrets import SecretProtector


class _SecretCodec(Protocol):
    def protect(self, value: str) -> str:
        ...

    def unprotect(self, value: str) -> str:
        ...


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _private_bytes(key: Ed25519PrivateKey | X25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def _public_bytes(key: Ed25519PublicKey | X25519PublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


@dataclass(frozen=True)
class SteamDeviceIdentity:
    device_id: str
    steam_id: str
    signing_key: Ed25519PrivateKey
    agreement_key: X25519PrivateKey

    @property
    def signing_public_key(self) -> str:
        return _encode(_public_bytes(self.signing_key.public_key()))

    @property
    def agreement_public_key(self) -> str:
        return _encode(_public_bytes(self.agreement_key.public_key()))

    def sign(self, payload: bytes) -> str:
        return _encode(self.signing_key.sign(payload))

    def shared_secret(self, peer_public_key: str) -> bytes:
        return self.agreement_key.exchange(
            X25519PublicKey.from_public_bytes(_decode(peer_public_key))
        )


class SteamDeviceIdentityStore:
    """Persists per-device private keys protected for the Windows user."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: Path | None = None,
        *,
        protector: _SecretCodec = SecretProtector,
    ) -> None:
        self.path = path or (
            AppConfig.get_data_directory() / "steam-device-identity.json"
        )
        self.protector = protector

    def load_or_create(self, steam_id: str) -> SteamDeviceIdentity:
        normalized_steam_id = self._steam_id(steam_id)
        if self.path.exists():
            return self._load(normalized_steam_id)

        identity = SteamDeviceIdentity(
            device_id=str(uuid.uuid4()),
            steam_id=normalized_steam_id,
            signing_key=Ed25519PrivateKey.generate(),
            agreement_key=X25519PrivateKey.generate(),
        )
        self._save(identity)
        return identity

    def _load(self, expected_steam_id: str) -> SteamDeviceIdentity:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError("unsupported identity schema")
            steam_id = self._steam_id(data["steam_id"])
            if steam_id != expected_steam_id:
                raise ValueError(
                    "This Save Shift device identity belongs to a different "
                    "Steam account."
                )
            device_id = str(uuid.UUID(data["device_id"]))
            signing_raw = _decode(
                self.protector.unprotect(data["signing_key_protected"])
            )
            agreement_raw = _decode(
                self.protector.unprotect(data["agreement_key_protected"])
            )
            return SteamDeviceIdentity(
                device_id=device_id,
                steam_id=steam_id,
                signing_key=Ed25519PrivateKey.from_private_bytes(signing_raw),
                agreement_key=X25519PrivateKey.from_private_bytes(agreement_raw),
            )
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("The stored Steam device identity is invalid.") from error

    def _save(self, identity: SteamDeviceIdentity) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": self.SCHEMA_VERSION,
            "device_id": identity.device_id,
            "steam_id": identity.steam_id,
            "signing_key_protected": self.protector.protect(
                _encode(_private_bytes(identity.signing_key))
            ),
            "agreement_key_protected": self.protector.protect(
                _encode(_private_bytes(identity.agreement_key))
            ),
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _steam_id(value: object) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("Steam returned an invalid account identifier.")
        return normalized
