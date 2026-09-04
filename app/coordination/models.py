from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import binascii
import json
from urllib.parse import urlparse

from app.package_transport.models import PackageArtifact


def parse_utc_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"Invalid UTC timestamp: {value}") from error

    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a UTC offset: {value}")

    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class PairedDevice:
    device_id: str
    device_token: str
    administrator: bool = False


@dataclass(frozen=True)
class GroupLeaveResult:
    group_empty: bool


@dataclass(frozen=True)
class CoordinationDevice:
    device_id: str
    device_name: str
    created_at_utc: datetime
    revoked: bool
    administrator: bool

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CoordinationDevice":
        device_id = data.get("device_id")
        device_name = data.get("device_name")
        created_at = data.get("created_at_utc")
        revoked = data.get("revoked")
        administrator = data.get("administrator")

        if not isinstance(device_id, str) or not device_id:
            raise ValueError("Device response is missing device_id.")
        if not isinstance(device_name, str) or not device_name:
            raise ValueError("Device response is missing device_name.")
        if not isinstance(created_at, str) or not created_at:
            raise ValueError("Device response is missing created_at_utc.")
        if not isinstance(revoked, bool) or not isinstance(administrator, bool):
            raise ValueError("Device response has invalid state.")

        return cls(
            device_id=device_id,
            device_name=device_name,
            created_at_utc=parse_utc_datetime(created_at),
            revoked=revoked,
            administrator=administrator,
        )


@dataclass(frozen=True)
class GroupInvitation:
    provider_url: str
    invitation_token: str
    expires_at_utc: datetime

    PREFIX = "saveshift-invite-v1:"

    def to_text(self) -> str:
        payload = json.dumps(
            {
                "provider_url": self.provider_url,
                "invitation_token": self.invitation_token,
                "expires_at_utc": self.expires_at_utc.astimezone(UTC).isoformat(),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        return f"{self.PREFIX}{encoded}"

    @classmethod
    def from_text(cls, value: str) -> "GroupInvitation":
        normalized = value.strip()

        if not normalized.startswith(cls.PREFIX):
            raise ValueError("This is not a Save Shift group invitation.")

        encoded = normalized[len(cls.PREFIX) :]
        encoded += "=" * (-len(encoded) % 4)

        try:
            data = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("The Save Shift invitation is invalid.") from error

        if not isinstance(data, dict):
            raise ValueError("The Save Shift invitation is invalid.")

        provider_url = data.get("provider_url")
        token = data.get("invitation_token")
        expires_at = data.get("expires_at_utc")

        if not isinstance(provider_url, str) or not _is_safe_provider_url(provider_url):
            raise ValueError("The invitation provider URL is invalid.")
        if not isinstance(token, str) or not token:
            raise ValueError("The invitation token is missing.")
        if not isinstance(expires_at, str):
            raise ValueError("The invitation expiration is missing.")

        return cls(
            provider_url=provider_url.rstrip("/"),
            invitation_token=token,
            expires_at_utc=parse_utc_datetime(expires_at),
        )


def _is_safe_provider_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    local = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "localhost",
    }
    return bool(
        parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and (parsed.scheme == "https" or local)
    )


@dataclass(frozen=True)
class LockLease:
    project_uuid: str
    lease_id: str
    fencing_token: int
    owner_device_id: str
    owner_display_name: str
    acquired_at_utc: datetime
    expires_at_utc: datetime

    @property
    def expired(self) -> bool:
        return self.expires_at_utc <= datetime.now(UTC)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "LockLease":
        required_strings = (
            "project_uuid",
            "lease_id",
            "owner_device_id",
            "owner_display_name",
            "acquired_at_utc",
            "expires_at_utc",
        )

        for field_name in required_strings:
            if not isinstance(data.get(field_name), str) or not data[field_name]:
                raise ValueError(f"Lock response is missing {field_name}.")

        fencing_token = data.get("fencing_token")

        if not isinstance(fencing_token, int) or isinstance(fencing_token, bool):
            raise ValueError("Lock response has an invalid fencing_token.")

        return cls(
            project_uuid=str(data["project_uuid"]),
            lease_id=str(data["lease_id"]),
            fencing_token=fencing_token,
            owner_device_id=str(data["owner_device_id"]),
            owner_display_name=str(data["owner_display_name"]),
            acquired_at_utc=parse_utc_datetime(str(data["acquired_at_utc"])),
            expires_at_utc=parse_utc_datetime(str(data["expires_at_utc"])),
        )


@dataclass(frozen=True)
class PackageCatalogMetadata:
    project_name: str
    game_id: str
    created_by: str


@dataclass(frozen=True)
class CatalogPackage:
    catalog_id: str
    artifact: PackageArtifact
    published_by_device_id: str
    published_at_utc: datetime
    metadata: PackageCatalogMetadata | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CatalogPackage":
        required_strings = (
            "catalog_id",
            "transport_name",
            "remote_id",
            "project_uuid",
            "package_checksum",
            "encryption_key_id",
            "published_by_device_id",
            "published_at_utc",
        )

        for field_name in required_strings:
            if not isinstance(data.get(field_name), str) or not data[field_name]:
                raise ValueError(f"Package response is missing {field_name}.")

        project_version = data.get("project_version")
        package_size_bytes = data.get("package_size_bytes")

        if (
            not isinstance(project_version, int)
            or isinstance(project_version, bool)
            or project_version < 1
        ):
            raise ValueError("Package response has an invalid project_version.")
        if (
            not isinstance(package_size_bytes, int)
            or isinstance(package_size_bytes, bool)
            or package_size_bytes < 1
        ):
            raise ValueError("Package response has an invalid package_size_bytes.")

        checksum = str(data["package_checksum"])

        if len(checksum) != 64 or any(
            character not in "0123456789abcdefABCDEF"
            for character in checksum
        ):
            raise ValueError("Package response has an invalid package_checksum.")

        metadata_values = (
            data.get("project_name"),
            data.get("game_id"),
            data.get("created_by"),
        )
        metadata: PackageCatalogMetadata | None = None

        if any(value is not None for value in metadata_values):
            if not all(
                isinstance(value, str) and bool(value.strip())
                for value in metadata_values
            ):
                raise ValueError("Package response has invalid display metadata.")
            metadata = PackageCatalogMetadata(
                project_name=str(metadata_values[0]).strip(),
                game_id=str(metadata_values[1]).strip(),
                created_by=str(metadata_values[2]).strip(),
            )

        return cls(
            catalog_id=str(data["catalog_id"]),
            artifact=PackageArtifact(
                transport_name=str(data["transport_name"]),
                remote_id=str(data["remote_id"]),
                project_uuid=str(data["project_uuid"]),
                project_version=project_version,
                package_checksum=checksum.lower(),
                package_size_bytes=package_size_bytes,
                encryption_key_id=str(data["encryption_key_id"]),
            ),
            published_by_device_id=str(data["published_by_device_id"]),
            published_at_utc=parse_utc_datetime(str(data["published_at_utc"])),
            metadata=metadata,
        )


@dataclass(frozen=True)
class PackageEncryptionKey:
    key_id: str
    algorithm: str
    key_material: bytes

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PackageEncryptionKey":
        algorithm = data.get("algorithm")
        key_id = data.get("key_id")
        encoded_key = data.get("key_material")

        if not isinstance(key_id, str) or not key_id:
            raise ValueError("Package key identifier is missing.")
        if algorithm != "AES-256-GCM":
            raise ValueError("Package key uses an unsupported algorithm.")
        if not isinstance(encoded_key, str) or not encoded_key:
            raise ValueError("Package key material is missing.")

        try:
            padded = encoded_key + "=" * (-len(encoded_key) % 4)
            key_material = base64.b64decode(
                padded,
                altchars=b"-_",
                validate=True,
            )
        except (ValueError, binascii.Error) as error:
            raise ValueError("Package key material is invalid.") from error

        if len(key_material) != 32:
            raise ValueError("Package key must contain 256 bits.")

        return cls(
            key_id=key_id,
            algorithm=algorithm,
            key_material=key_material,
        )
