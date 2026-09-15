from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.steam.device_identity import SteamDeviceIdentity, _decode
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_security import _canonical_json


@dataclass(frozen=True)
class SteamPackageDescriptor:
    """Signed, immutable ancestry record for one encrypted Workshop package."""

    schema_version: int
    group_id: str
    project_uuid: str
    project_version: int
    version_id: str
    parent_descriptor_hash: str
    publisher_steam_id: str
    publisher_device_id: str
    publisher_certificate_id: str
    published_at_utc: str
    encrypted_payload_checksum: str
    package_checksum: str
    package_size_bytes: int
    workshop_item_id: str
    key_epoch: int
    project_name: str
    game_id: str
    created_by: str
    signature: str

    SCHEMA_VERSION = 1
    METADATA_KIND = "saveshift-package-descriptor"

    @classmethod
    def create(
        cls,
        *,
        manifest: SteamGroupManifest,
        publisher: SteamDeviceIdentity,
        project_uuid: str,
        project_version: int,
        parent_descriptor_hash: str | None,
        encrypted_payload_checksum: str,
        package_checksum: str,
        package_size_bytes: int,
        workshop_item_id: str,
        project_name: str,
        game_id: str,
        created_by: str,
        published_at: datetime | None = None,
        version_id: str | None = None,
    ) -> "SteamPackageDescriptor":
        certificate = next(
            (
                item
                for item in manifest.active_members
                if item.device_id == publisher.device_id
                and item.steam_id == publisher.steam_id
                and item.signing_public_key == publisher.signing_public_key
            ),
            None,
        )
        if certificate is None:
            raise ValueError("The publisher is not an active member of this group.")
        unsigned = cls(
            schema_version=cls.SCHEMA_VERSION,
            group_id=str(uuid.UUID(manifest.group_id)),
            project_uuid=str(uuid.UUID(project_uuid)),
            project_version=project_version,
            version_id=str(uuid.UUID(version_id)) if version_id else str(uuid.uuid4()),
            parent_descriptor_hash=cls._parent_hash(parent_descriptor_hash),
            publisher_steam_id=publisher.steam_id,
            publisher_device_id=publisher.device_id,
            publisher_certificate_id=certificate.certificate_id,
            published_at_utc=(published_at or datetime.now(UTC))
            .astimezone(UTC)
            .isoformat(),
            encrypted_payload_checksum=cls._checksum(
                encrypted_payload_checksum,
                "encrypted payload",
            ),
            package_checksum=cls._checksum(package_checksum, "package"),
            package_size_bytes=package_size_bytes,
            workshop_item_id=cls._workshop_item_id(workshop_item_id),
            key_epoch=manifest.key_epoch,
            project_name=cls._text(project_name, "Project name"),
            game_id=cls._text(game_id, "Game identifier"),
            created_by=cls._text(created_by, "Publisher name"),
            signature="",
        )
        unsigned._validate_shape(require_signature=False)
        return cls(**{**asdict(unsigned), "signature": publisher.sign(unsigned._payload())})

    @property
    def descriptor_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_dict())).hexdigest()

    def verify(
        self,
        manifest: SteamGroupManifest,
        *,
        expected_workshop_item_id: str | None = None,
    ) -> bool:
        try:
            self._validate_shape()
            if not manifest.verify() or self.group_id != manifest.group_id:
                return False
            if self.key_epoch < 1 or self.key_epoch > manifest.key_epoch:
                return False
            if (
                expected_workshop_item_id is not None
                and self.workshop_item_id
                != self._workshop_item_id(expected_workshop_item_id)
            ):
                return False
            member = next(
                (
                    item
                    for item in manifest.active_members
                    if item.certificate_id == self.publisher_certificate_id
                    and item.device_id == self.publisher_device_id
                    and item.steam_id == self.publisher_steam_id
                ),
                None,
            )
            if member is None:
                return False
            Ed25519PublicKey.from_public_bytes(
                _decode(member.signing_public_key)
            ).verify(_decode(self.signature), self._payload())
        except (InvalidSignature, TypeError, ValueError):
            return False
        return True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self, *, compact: bool = False) -> str:
        if compact:
            return json.dumps(
                {"kind": self.METADATA_KIND, "descriptor": self.to_dict()},
                sort_keys=True,
                separators=(",", ":"),
            )
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, value: str | bytes) -> "SteamPackageDescriptor":
        try:
            raw = json.loads(value)
            if isinstance(raw, dict) and raw.get("kind") == cls.METADATA_KIND:
                raw = raw["descriptor"]
            if not isinstance(raw, dict):
                raise ValueError("descriptor must be an object")
            descriptor = cls(
                schema_version=int(raw["schema_version"]),
                group_id=str(uuid.UUID(str(raw["group_id"]))),
                project_uuid=str(uuid.UUID(str(raw["project_uuid"]))),
                project_version=int(raw["project_version"]),
                version_id=str(uuid.UUID(str(raw["version_id"]))),
                parent_descriptor_hash=cls._parent_hash(
                    raw["parent_descriptor_hash"]
                ),
                publisher_steam_id=str(raw["publisher_steam_id"]),
                publisher_device_id=str(uuid.UUID(str(raw["publisher_device_id"]))),
                publisher_certificate_id=str(
                    uuid.UUID(str(raw["publisher_certificate_id"]))
                ),
                published_at_utc=str(raw["published_at_utc"]),
                encrypted_payload_checksum=cls._checksum(
                    raw["encrypted_payload_checksum"],
                    "encrypted payload",
                ),
                package_checksum=cls._checksum(raw["package_checksum"], "package"),
                package_size_bytes=int(raw["package_size_bytes"]),
                workshop_item_id=cls._workshop_item_id(raw["workshop_item_id"]),
                key_epoch=int(raw["key_epoch"]),
                project_name=cls._text(raw["project_name"], "Project name"),
                game_id=cls._text(raw["game_id"], "Game identifier"),
                created_by=cls._text(raw["created_by"], "Publisher name"),
                signature=str(raw["signature"]),
            )
            descriptor._validate_shape()
            return descriptor
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("The Steam package descriptor is invalid.") from error

    def _payload(self) -> bytes:
        value = self.to_dict()
        value.pop("signature")
        return _canonical_json(value)

    def _validate_shape(self, *, require_signature: bool = True) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError("Unsupported Steam package descriptor version.")
        uuid.UUID(self.group_id)
        uuid.UUID(self.project_uuid)
        uuid.UUID(self.version_id)
        uuid.UUID(self.publisher_device_id)
        uuid.UUID(self.publisher_certificate_id)
        if not self.publisher_steam_id.isdigit() or int(self.publisher_steam_id) < 1:
            raise ValueError("The descriptor publisher Steam ID is invalid.")
        if self.project_version < 1 or self.package_size_bytes < 1:
            raise ValueError("The descriptor package version or size is invalid.")
        if self.key_epoch < 1:
            raise ValueError("The descriptor key epoch is invalid.")
        self._parent_hash(self.parent_descriptor_hash)
        self._checksum(self.encrypted_payload_checksum, "encrypted payload")
        self._checksum(self.package_checksum, "package")
        self._workshop_item_id(self.workshop_item_id)
        self._text(self.project_name, "Project name")
        self._text(self.game_id, "Game identifier")
        self._text(self.created_by, "Publisher name")
        timestamp = datetime.fromisoformat(self.published_at_utc)
        if timestamp.tzinfo is None:
            raise ValueError("The descriptor timestamp must include a timezone.")
        if require_signature and len(_decode(self.signature)) != 64:
            raise ValueError("The descriptor signature is invalid.")

    @staticmethod
    def _checksum(value: object, label: str) -> str:
        normalized = str(value).strip().lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError(f"The {label} checksum is invalid.")
        return normalized

    @staticmethod
    def _parent_hash(value: object | None) -> str:
        normalized = "" if value is None else str(value).strip().lower()
        if normalized and (
            len(normalized) != 64
            or any(character not in "0123456789abcdef" for character in normalized)
        ):
            raise ValueError("The parent descriptor hash is invalid.")
        return normalized

    @staticmethod
    def _workshop_item_id(value: object) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("The Workshop item identifier is invalid.")
        return normalized

    @staticmethod
    def _text(value: object, label: str) -> str:
        normalized = str(value).strip()
        if not normalized or len(normalized) > 256:
            raise ValueError(f"{label} is invalid.")
        return normalized
