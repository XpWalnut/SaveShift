from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.steam.device_identity import SteamDeviceIdentity, _decode
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_security import _canonical_json


@dataclass(frozen=True)
class SteamMemberPackageIndex:
    """A member-signed list of that device's unlisted package item IDs."""

    schema_version: int
    group_id: str
    publisher_steam_id: str
    publisher_device_id: str
    workshop_item_id: str
    revision: int
    package_item_ids: tuple[str, ...]
    updated_at_utc: str
    signature: str

    SCHEMA_VERSION = 1
    METADATA_KIND = "saveshift-member-package-index"

    @classmethod
    def create(
        cls,
        *,
        group_id: str,
        publisher: SteamDeviceIdentity,
        workshop_item_id: str,
        updated_at: datetime | None = None,
    ) -> "SteamMemberPackageIndex":
        unsigned = cls(
            schema_version=cls.SCHEMA_VERSION,
            group_id=str(uuid.UUID(group_id)),
            publisher_steam_id=publisher.steam_id,
            publisher_device_id=publisher.device_id,
            workshop_item_id=cls._item_id(workshop_item_id),
            revision=1,
            package_item_ids=(),
            updated_at_utc=cls._timestamp(updated_at),
            signature="",
        )
        return unsigned._signed(publisher)

    def add(
        self,
        package_item_id: str,
        publisher: SteamDeviceIdentity,
        *,
        updated_at: datetime | None = None,
    ) -> "SteamMemberPackageIndex":
        self._require_publisher(publisher)
        item_id = self._item_id(package_item_id)
        package_ids = tuple(sorted(set((*self.package_item_ids, item_id)), key=int))
        if package_ids == self.package_item_ids:
            return self
        return replace(
            self,
            revision=self.revision + 1,
            package_item_ids=package_ids,
            updated_at_utc=self._timestamp(updated_at),
            signature="",
        )._signed(publisher)

    def verify(
        self,
        manifest: SteamGroupManifest,
        *,
        expected_workshop_item_id: str | None = None,
    ) -> bool:
        try:
            self._validate()
            if not manifest.verify() or self.group_id != manifest.group_id:
                return False
            if expected_workshop_item_id is not None and self.workshop_item_id != str(
                expected_workshop_item_id
            ):
                return False
            reference = next(
                (
                    item
                    for item in manifest.member_package_indexes
                    if item.device_id == self.publisher_device_id
                ),
                None,
            )
            member = next(
                (
                    item
                    for item in manifest.active_members
                    if item.device_id == self.publisher_device_id
                ),
                None,
            )
            if (
                reference is None
                or member is None
                or reference.steam_id != self.publisher_steam_id
                or reference.workshop_item_id != self.workshop_item_id
                or member.steam_id != self.publisher_steam_id
            ):
                return False
            Ed25519PublicKey.from_public_bytes(
                _decode(member.signing_public_key)
            ).verify(_decode(self.signature), self._signing_payload())
        except (InvalidSignature, TypeError, ValueError):
            return False
        return True

    def to_json(self, *, compact: bool = False) -> str:
        value = {
            "kind": self.METADATA_KIND,
            "index": self._data(include_signature=True),
        }
        if compact:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return json.dumps(value, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, value: str | bytes) -> "SteamMemberPackageIndex":
        try:
            raw = json.loads(value)
            if not isinstance(raw, dict):
                raise ValueError("index must be an object")
            if raw.get("kind") == cls.METADATA_KIND:
                raw = raw["index"]
            if not isinstance(raw, dict):
                raise ValueError("index body must be an object")
            package_ids = raw["package_item_ids"]
            if not isinstance(package_ids, list):
                raise ValueError("package item identifiers must be a list")
            index = cls(
                schema_version=int(raw["schema_version"]),
                group_id=str(uuid.UUID(str(raw["group_id"]))),
                publisher_steam_id=str(raw["publisher_steam_id"]),
                publisher_device_id=str(uuid.UUID(str(raw["publisher_device_id"]))),
                workshop_item_id=cls._item_id(str(raw["workshop_item_id"])),
                revision=int(raw["revision"]),
                package_item_ids=tuple(cls._item_id(str(item)) for item in package_ids),
                updated_at_utc=str(raw["updated_at_utc"]),
                signature=str(raw["signature"]),
            )
            index._validate()
            return index
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("The Steam member package index is invalid.") from error

    def _signed(self, publisher: SteamDeviceIdentity) -> "SteamMemberPackageIndex":
        self._require_publisher(publisher)
        normalized = replace(
            self,
            package_item_ids=tuple(sorted(set(self.package_item_ids), key=int)),
        )
        return replace(
            normalized,
            signature=publisher.sign(normalized._signing_payload()),
        )

    def _require_publisher(self, publisher: SteamDeviceIdentity) -> None:
        if (
            publisher.device_id != self.publisher_device_id
            or publisher.steam_id != self.publisher_steam_id
        ):
            raise ValueError("Only this package index's publisher can change it.")

    def _signing_payload(self) -> bytes:
        return _canonical_json(self._data(include_signature=False))

    def _data(self, *, include_signature: bool) -> dict[str, object]:
        value = asdict(self)
        if not include_signature:
            value.pop("signature")
        return value

    def _validate(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError("Unsupported Steam member package index version.")
        uuid.UUID(self.group_id)
        uuid.UUID(self.publisher_device_id)
        if not self.publisher_steam_id.isdigit() or int(self.publisher_steam_id) < 1:
            raise ValueError("The package index Steam account is invalid.")
        self._item_id(self.workshop_item_id)
        if self.revision < 1:
            raise ValueError("The package index revision is invalid.")
        if len(self.package_item_ids) != len(set(self.package_item_ids)):
            raise ValueError("The package index contains duplicate items.")
        for item_id in self.package_item_ids:
            self._item_id(item_id)
        timestamp = datetime.fromisoformat(self.updated_at_utc)
        if timestamp.tzinfo is None:
            raise ValueError("The package index timestamp must include a timezone.")
        if len(_decode(self.signature)) != 64:
            raise ValueError("The package index signature is invalid.")

    @staticmethod
    def _item_id(value: str) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("The Workshop item identifier is invalid.")
        return normalized

    @staticmethod
    def _timestamp(value: datetime | None) -> str:
        timestamp = value or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("The package index timestamp must include a timezone.")
        return timestamp.astimezone(UTC).isoformat()
