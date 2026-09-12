from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import os
from typing import Iterable
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.steam.device_identity import SteamDeviceIdentity, _decode
from app.steam.group_security import (
    SteamGroupKeyEnvelope,
    SteamMembershipCertificate,
    _canonical_json,
)


@dataclass(frozen=True)
class SteamGroupManifest:
    schema_version: int
    group_id: str
    name: str
    revision: int
    administrator_steam_id: str
    administrator_device_id: str
    administrator_signing_public_key: str
    key_epoch: int
    members: tuple[SteamMembershipCertificate, ...]
    revoked_certificate_ids: tuple[str, ...]
    key_envelopes: tuple[SteamGroupKeyEnvelope, ...]
    updated_at_utc: str
    signature: str

    SCHEMA_VERSION = 1

    @classmethod
    def create(
        cls,
        name: str,
        administrator: SteamDeviceIdentity,
        *,
        group_key: bytes | None = None,
        updated_at: datetime | None = None,
    ) -> tuple["SteamGroupManifest", bytes]:
        normalized_name = cls._name(name)
        key = group_key or os.urandom(32)
        if len(key) != 32:
            raise ValueError("A Steam group key must contain 256 bits.")
        group_id = str(uuid.uuid4())
        certificate = SteamMembershipCertificate.issue(
            group_id=group_id,
            member=administrator,
            administrator=administrator,
            issued_at=updated_at,
        )
        envelope = SteamGroupKeyEnvelope.seal(
            group_id=group_id,
            key_epoch=1,
            recipient_device_id=administrator.device_id,
            recipient_agreement_public_key=administrator.agreement_public_key,
            group_key=key,
        )
        unsigned = cls(
            schema_version=cls.SCHEMA_VERSION,
            group_id=group_id,
            name=normalized_name,
            revision=1,
            administrator_steam_id=administrator.steam_id,
            administrator_device_id=administrator.device_id,
            administrator_signing_public_key=administrator.signing_public_key,
            key_epoch=1,
            members=(certificate,),
            revoked_certificate_ids=(),
            key_envelopes=(envelope,),
            updated_at_utc=cls._timestamp(updated_at),
            signature="",
        )
        return unsigned._signed(administrator), key

    def add_member(
        self,
        member: SteamDeviceIdentity,
        group_key: bytes,
        administrator: SteamDeviceIdentity,
        *,
        updated_at: datetime | None = None,
    ) -> "SteamGroupManifest":
        return self.add_public_member(
            steam_id=member.steam_id,
            device_id=member.device_id,
            signing_public_key=member.signing_public_key,
            agreement_public_key=member.agreement_public_key,
            group_key=group_key,
            administrator=administrator,
            updated_at=updated_at,
        )

    def add_public_member(
        self,
        *,
        steam_id: str,
        device_id: str,
        signing_public_key: str,
        agreement_public_key: str,
        group_key: bytes,
        administrator: SteamDeviceIdentity,
        updated_at: datetime | None = None,
    ) -> "SteamGroupManifest":
        self._require_administrator(administrator)
        if len(group_key) != 32:
            raise ValueError("A Steam group key must contain 256 bits.")
        normalized_device_id = str(uuid.UUID(device_id))
        if any(
            item.device_id == normalized_device_id for item in self.active_members
        ):
            raise ValueError("This device is already a member of the group.")
        certificate = SteamMembershipCertificate.issue_public_device(
            group_id=self.group_id,
            steam_id=steam_id,
            device_id=normalized_device_id,
            signing_public_key=signing_public_key,
            agreement_public_key=agreement_public_key,
            administrator=administrator,
            issued_at=updated_at,
        )
        envelope = SteamGroupKeyEnvelope.seal(
            group_id=self.group_id,
            key_epoch=self.key_epoch,
            recipient_device_id=normalized_device_id,
            recipient_agreement_public_key=agreement_public_key,
            group_key=group_key,
        )
        updated = replace(
            self,
            revision=self.revision + 1,
            members=self.members + (certificate,),
            key_envelopes=self.key_envelopes + (envelope,),
            updated_at_utc=self._timestamp(updated_at),
            signature="",
        )
        return updated._signed(administrator)

    def revoke_member(
        self,
        device_id: str,
        administrator: SteamDeviceIdentity,
        *,
        replacement_group_key: bytes | None = None,
        updated_at: datetime | None = None,
    ) -> tuple["SteamGroupManifest", bytes]:
        self._require_administrator(administrator)
        normalized_device_id = str(uuid.UUID(device_id))
        if normalized_device_id == self.administrator_device_id:
            raise ValueError("The group administrator cannot revoke itself.")
        certificate = next(
            (
                item
                for item in self.active_members
                if item.device_id == normalized_device_id
            ),
            None,
        )
        if certificate is None:
            raise ValueError("This device is not an active group member.")
        key = replacement_group_key or os.urandom(32)
        if len(key) != 32:
            raise ValueError("A Steam group key must contain 256 bits.")
        epoch = self.key_epoch + 1
        revoked = tuple(
            sorted((*self.revoked_certificate_ids, certificate.certificate_id))
        )
        active_after = tuple(
            item
            for item in self.members
            if item.certificate_id not in set(revoked)
        )
        envelopes = tuple(
            SteamGroupKeyEnvelope.seal(
                group_id=self.group_id,
                key_epoch=epoch,
                recipient_device_id=item.device_id,
                recipient_agreement_public_key=item.agreement_public_key,
                group_key=key,
            )
            for item in active_after
        )
        updated = replace(
            self,
            revision=self.revision + 1,
            key_epoch=epoch,
            revoked_certificate_ids=revoked,
            key_envelopes=envelopes,
            updated_at_utc=self._timestamp(updated_at),
            signature="",
        )
        return updated._signed(administrator), key

    @property
    def active_members(self) -> tuple[SteamMembershipCertificate, ...]:
        revoked = set(self.revoked_certificate_ids)
        return tuple(
            member
            for member in self.members
            if member.certificate_id not in revoked
        )

    def group_key_for(self, identity: SteamDeviceIdentity) -> bytes:
        if not any(member.device_id == identity.device_id for member in self.active_members):
            raise ValueError("This device is not an active group member.")
        envelope = next(
            (
                item
                for item in self.key_envelopes
                if item.recipient_device_id == identity.device_id
                and item.key_epoch == self.key_epoch
            ),
            None,
        )
        if envelope is None:
            raise ValueError("The manifest has no current key for this device.")
        return envelope.open(identity)

    def verify(self) -> bool:
        try:
            self._validate()
            Ed25519PublicKey.from_public_bytes(
                _decode(self.administrator_signing_public_key)
            ).verify(_decode(self.signature), self._signing_payload())
        except (InvalidSignature, TypeError, ValueError):
            return False
        return True

    def to_json(self) -> str:
        if not self.verify():
            raise ValueError("The Steam group manifest signature is invalid.")
        return json.dumps(self._data(include_signature=True), indent=2) + "\n"

    @classmethod
    def from_json(cls, value: str | bytes) -> "SteamGroupManifest":
        try:
            raw = json.loads(value)
            if not isinstance(raw, dict):
                raise ValueError("manifest must be an object")
            members = cls._objects(raw["members"], SteamMembershipCertificate)
            envelopes = cls._objects(raw["key_envelopes"], SteamGroupKeyEnvelope)
            revoked_raw = raw["revoked_certificate_ids"]
            if not isinstance(revoked_raw, list):
                raise ValueError("revocations must be a list")
            manifest = cls(
                schema_version=int(raw["schema_version"]),
                group_id=str(uuid.UUID(str(raw["group_id"]))),
                name=cls._name(str(raw["name"])),
                revision=int(raw["revision"]),
                administrator_steam_id=str(raw["administrator_steam_id"]),
                administrator_device_id=str(
                    uuid.UUID(str(raw["administrator_device_id"]))
                ),
                administrator_signing_public_key=str(
                    raw["administrator_signing_public_key"]
                ),
                key_epoch=int(raw["key_epoch"]),
                members=tuple(members),
                revoked_certificate_ids=tuple(
                    str(uuid.UUID(str(item))) for item in revoked_raw
                ),
                key_envelopes=tuple(envelopes),
                updated_at_utc=str(raw["updated_at_utc"]),
                signature=str(raw["signature"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("The Steam group manifest is invalid.") from error
        if not manifest.verify():
            raise ValueError("The Steam group manifest signature is invalid.")
        return manifest

    def _signed(self, administrator: SteamDeviceIdentity) -> "SteamGroupManifest":
        self._require_administrator(administrator)
        normalized = replace(
            self,
            members=tuple(
                sorted(self.members, key=lambda item: item.certificate_id)
            ),
            revoked_certificate_ids=tuple(sorted(self.revoked_certificate_ids)),
            key_envelopes=tuple(
                sorted(
                    self.key_envelopes,
                    key=lambda item: (item.key_epoch, item.recipient_device_id),
                )
            ),
        )
        signed = replace(
            normalized,
            signature=administrator.sign(normalized._signing_payload()),
        )
        if not signed.verify():
            raise ValueError("Could not create a valid Steam group manifest.")
        return signed

    def _signing_payload(self) -> bytes:
        return _canonical_json(self._data(include_signature=False))

    def _data(self, *, include_signature: bool) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "group_id": self.group_id,
            "name": self.name,
            "revision": self.revision,
            "administrator_steam_id": self.administrator_steam_id,
            "administrator_device_id": self.administrator_device_id,
            "administrator_signing_public_key": self.administrator_signing_public_key,
            "key_epoch": self.key_epoch,
            "members": [
                member.to_dict()
                for member in sorted(self.members, key=lambda item: item.certificate_id)
            ],
            "revoked_certificate_ids": sorted(self.revoked_certificate_ids),
            "key_envelopes": [
                envelope.to_dict()
                for envelope in sorted(
                    self.key_envelopes,
                    key=lambda item: (item.key_epoch, item.recipient_device_id),
                )
            ],
            "updated_at_utc": self.updated_at_utc,
        }
        if include_signature:
            value["signature"] = self.signature
        return value

    def _validate(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError("Unsupported Steam group manifest version.")
        uuid.UUID(self.group_id)
        uuid.UUID(self.administrator_device_id)
        self._name(self.name)
        if self.revision < 1 or self.key_epoch < 1:
            raise ValueError("The manifest revision or key epoch is invalid.")
        if not self.administrator_steam_id.isdigit():
            raise ValueError("The administrator Steam account is invalid.")
        if len(_decode(self.administrator_signing_public_key)) != 32:
            raise ValueError("The administrator signing key is invalid.")
        timestamp = datetime.fromisoformat(self.updated_at_utc)
        if timestamp.tzinfo is None:
            raise ValueError("The manifest timestamp must include a timezone.")
        if len(_decode(self.signature)) != 64:
            raise ValueError("The manifest signature is invalid.")
        certificate_ids = [item.certificate_id for item in self.members]
        device_ids = [item.device_id for item in self.active_members]
        if len(certificate_ids) != len(set(certificate_ids)):
            raise ValueError("The manifest contains duplicate certificates.")
        if len(device_ids) != len(set(device_ids)):
            raise ValueError("The manifest contains duplicate active devices.")
        revoked = set(self.revoked_certificate_ids)
        if not revoked.issubset(set(certificate_ids)):
            raise ValueError("The manifest revokes an unknown certificate.")
        for member in self.members:
            if member.group_id != self.group_id:
                raise ValueError("A membership certificate belongs to another group.")
            if member.issued_by_device_id != self.administrator_device_id:
                raise ValueError("A membership certificate has the wrong issuer.")
            if not member.verify(self.administrator_signing_public_key):
                raise ValueError("A membership certificate signature is invalid.")
        administrator = next(
            (
                item
                for item in self.active_members
                if item.device_id == self.administrator_device_id
            ),
            None,
        )
        if (
            administrator is None
            or administrator.steam_id != self.administrator_steam_id
            or administrator.signing_public_key
            != self.administrator_signing_public_key
        ):
            raise ValueError("The administrator membership is invalid.")
        current_envelopes = tuple(
            item for item in self.key_envelopes if item.key_epoch == self.key_epoch
        )
        if {item.recipient_device_id for item in current_envelopes} != set(device_ids):
            raise ValueError("Current group-key envelopes do not match active members.")
        for envelope in self.key_envelopes:
            if envelope.group_id != self.group_id:
                raise ValueError("A group-key envelope belongs to another group.")

    def _require_administrator(self, identity: SteamDeviceIdentity) -> None:
        if (
            identity.device_id != self.administrator_device_id
            or identity.steam_id != self.administrator_steam_id
            or identity.signing_public_key != self.administrator_signing_public_key
        ):
            raise ValueError("Only this group's administrator can change the manifest.")

    @staticmethod
    def _name(value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("A Steam group name must contain 1 to 80 characters.")
        return normalized

    @staticmethod
    def _timestamp(value: datetime | None) -> str:
        timestamp = value or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("The manifest timestamp must include a timezone.")
        return timestamp.astimezone(UTC).isoformat()

    @staticmethod
    def _objects(
        value: object,
        model: type[SteamMembershipCertificate] | type[SteamGroupKeyEnvelope],
    ) -> Iterable[SteamMembershipCertificate | SteamGroupKeyEnvelope]:
        if not isinstance(value, list):
            raise ValueError("manifest collection must be a list")
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("manifest entry must be an object")
            yield model.from_dict(item)
