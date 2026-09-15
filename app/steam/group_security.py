from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.steam.device_identity import (
    SteamDeviceIdentity,
    _decode,
    _encode,
    _public_bytes,
)


def _canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class SteamMembershipCertificate:
    certificate_id: str
    group_id: str
    steam_id: str
    device_id: str
    signing_public_key: str
    agreement_public_key: str
    issued_at_utc: str
    issued_by_device_id: str
    signature: str

    @classmethod
    def issue(
        cls,
        *,
        group_id: str,
        member: SteamDeviceIdentity,
        administrator: SteamDeviceIdentity,
        issued_at: datetime | None = None,
    ) -> "SteamMembershipCertificate":
        return cls.issue_public_device(
            group_id=group_id,
            steam_id=member.steam_id,
            device_id=member.device_id,
            signing_public_key=member.signing_public_key,
            agreement_public_key=member.agreement_public_key,
            administrator=administrator,
            issued_at=issued_at,
        )

    @classmethod
    def issue_public_device(
        cls,
        *,
        group_id: str,
        steam_id: str,
        device_id: str,
        signing_public_key: str,
        agreement_public_key: str,
        administrator: SteamDeviceIdentity,
        issued_at: datetime | None = None,
    ) -> "SteamMembershipCertificate":
        normalized_steam_id = str(steam_id).strip()
        if not normalized_steam_id.isdigit() or int(normalized_steam_id) < 1:
            raise ValueError("A membership requires a valid Steam account.")
        normalized_device_id = str(uuid.UUID(device_id))
        if len(_decode(signing_public_key)) != 32:
            raise ValueError("A membership signing key is invalid.")
        if len(_decode(agreement_public_key)) != 32:
            raise ValueError("A membership agreement key is invalid.")
        unsigned = {
            "certificate_id": str(uuid.uuid4()),
            "group_id": str(uuid.UUID(group_id)),
            "steam_id": normalized_steam_id,
            "device_id": normalized_device_id,
            "signing_public_key": signing_public_key,
            "agreement_public_key": agreement_public_key,
            "issued_at_utc": (issued_at or datetime.now(UTC))
            .astimezone(UTC)
            .isoformat(),
            "issued_by_device_id": administrator.device_id,
        }
        return cls(**unsigned, signature=administrator.sign(_canonical_json(unsigned)))

    def verify(self, administrator_signing_public_key: str) -> bool:
        unsigned = asdict(self)
        signature = unsigned.pop("signature")
        try:
            Ed25519PublicKey.from_public_bytes(
                _decode(administrator_signing_public_key)
            ).verify(_decode(signature), _canonical_json(unsigned))
        except (InvalidSignature, ValueError):
            return False
        return True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "SteamMembershipCertificate":
        try:
            certificate = cls(
                certificate_id=str(uuid.UUID(str(value["certificate_id"]))),
                group_id=str(uuid.UUID(str(value["group_id"]))),
                steam_id=str(value["steam_id"]),
                device_id=str(uuid.UUID(str(value["device_id"]))),
                signing_public_key=str(value["signing_public_key"]),
                agreement_public_key=str(value["agreement_public_key"]),
                issued_at_utc=str(value["issued_at_utc"]),
                issued_by_device_id=str(uuid.UUID(str(value["issued_by_device_id"]))),
                signature=str(value["signature"]),
            )
            if not certificate.steam_id.isdigit():
                raise ValueError("invalid Steam account")
            datetime.fromisoformat(certificate.issued_at_utc)
            if len(_decode(certificate.signing_public_key)) != 32:
                raise ValueError("invalid signing key")
            if len(_decode(certificate.agreement_public_key)) != 32:
                raise ValueError("invalid agreement key")
            if len(_decode(certificate.signature)) != 64:
                raise ValueError("invalid signature")
            return certificate
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("The Steam membership certificate is invalid.") from error


@dataclass(frozen=True)
class SteamGroupKeyEnvelope:
    group_id: str
    key_epoch: int
    recipient_device_id: str
    ephemeral_public_key: str
    nonce: str
    ciphertext: str

    @classmethod
    def seal(
        cls,
        *,
        group_id: str,
        key_epoch: int,
        recipient_device_id: str,
        recipient_agreement_public_key: str,
        group_key: bytes,
    ) -> "SteamGroupKeyEnvelope":
        normalized_group_id = str(uuid.UUID(group_id))
        normalized_device_id = str(uuid.UUID(recipient_device_id))
        if key_epoch < 1 or len(group_key) != 32:
            raise ValueError("A group key envelope requires a valid epoch and 256-bit key.")
        ephemeral = X25519PrivateKey.generate()
        shared = ephemeral.exchange(
            X25519PublicKey.from_public_bytes(
                _decode(recipient_agreement_public_key)
            )
        )
        wrapping_key = cls._wrapping_key(shared, normalized_group_id, key_epoch)
        nonce = os.urandom(12)
        associated_data = cls._associated_data(
            normalized_group_id,
            key_epoch,
            normalized_device_id,
        )
        return cls(
            group_id=normalized_group_id,
            key_epoch=key_epoch,
            recipient_device_id=normalized_device_id,
            ephemeral_public_key=_encode(_public_bytes(ephemeral.public_key())),
            nonce=_encode(nonce),
            ciphertext=_encode(
                AESGCM(wrapping_key).encrypt(nonce, group_key, associated_data)
            ),
        )

    def open(self, recipient: SteamDeviceIdentity) -> bytes:
        if recipient.device_id != self.recipient_device_id:
            raise ValueError("This group key envelope belongs to another device.")
        shared = recipient.agreement_key.exchange(
            X25519PublicKey.from_public_bytes(_decode(self.ephemeral_public_key))
        )
        wrapping_key = self._wrapping_key(shared, self.group_id, self.key_epoch)
        return AESGCM(wrapping_key).decrypt(
            _decode(self.nonce),
            _decode(self.ciphertext),
            self._associated_data(
                self.group_id,
                self.key_epoch,
                self.recipient_device_id,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "SteamGroupKeyEnvelope":
        try:
            envelope = cls(
                group_id=str(uuid.UUID(str(value["group_id"]))),
                key_epoch=int(value["key_epoch"]),
                recipient_device_id=str(
                    uuid.UUID(str(value["recipient_device_id"]))
                ),
                ephemeral_public_key=str(value["ephemeral_public_key"]),
                nonce=str(value["nonce"]),
                ciphertext=str(value["ciphertext"]),
            )
            if envelope.key_epoch < 1:
                raise ValueError("invalid key epoch")
            if len(_decode(envelope.ephemeral_public_key)) != 32:
                raise ValueError("invalid ephemeral key")
            if len(_decode(envelope.nonce)) != 12:
                raise ValueError("invalid nonce")
            if len(_decode(envelope.ciphertext)) != 48:
                raise ValueError("invalid encrypted group key")
            return envelope
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("The Steam group key envelope is invalid.") from error

    @staticmethod
    def _wrapping_key(shared: bytes, group_id: str, key_epoch: int) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=uuid.UUID(group_id).bytes,
            info=f"SaveShift group key epoch {key_epoch}".encode("ascii"),
        ).derive(shared)

    @staticmethod
    def _associated_data(group_id: str, key_epoch: int, device_id: str) -> bytes:
        return _canonical_json(
            {
                "group_id": group_id,
                "key_epoch": key_epoch,
                "recipient_device_id": device_id,
            }
        )
