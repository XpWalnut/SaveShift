from dataclasses import dataclass
from datetime import UTC, datetime


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
