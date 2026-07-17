from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


MAX_JOURNAL_TITLE_LENGTH = 120
MAX_JOURNAL_BODY_LENGTH = 5000
MAX_JOURNAL_AUTHOR_LENGTH = 100


@dataclass(frozen=True)
class PackageJournalEntry:
    entry_uuid: str
    title: str
    body: str
    created_by: str
    created_at_utc: str
    project_version_number: int | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        body: str,
        created_by: str,
        project_version_number: int | None = None,
        entry_uuid: str | None = None,
        created_at_utc: datetime | None = None,
    ) -> "PackageJournalEntry":
        normalized_title = _required_text(
            title,
            "Journal title",
            MAX_JOURNAL_TITLE_LENGTH,
        )
        normalized_body = _required_text(
            body,
            "Journal entry",
            MAX_JOURNAL_BODY_LENGTH,
        )
        normalized_author = _required_text(
            created_by,
            "Journal author",
            MAX_JOURNAL_AUTHOR_LENGTH,
        )
        normalized_uuid = str(UUID(entry_uuid)) if entry_uuid else str(uuid4())
        created_at = created_at_utc or datetime.now(UTC)

        if created_at.tzinfo is None:
            raise ValueError("Journal timestamp must include a UTC offset.")

        if project_version_number is not None and project_version_number < 1:
            raise ValueError("Journal project version must be positive.")

        return cls(
            entry_uuid=normalized_uuid,
            title=normalized_title,
            body=normalized_body,
            created_by=normalized_author,
            created_at_utc=created_at.astimezone(UTC).isoformat(),
            project_version_number=project_version_number,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackageJournalEntry":
        if not isinstance(data, dict):
            raise ValueError("Journal entry must be an object.")

        created_at_value = data.get("created_at_utc")

        if not isinstance(created_at_value, str):
            raise ValueError("Journal timestamp is missing.")

        normalized_timestamp = (
            created_at_value[:-1] + "+00:00"
            if created_at_value.endswith("Z")
            else created_at_value
        )

        try:
            created_at = datetime.fromisoformat(normalized_timestamp)
        except ValueError as error:
            raise ValueError("Journal timestamp is invalid.") from error

        entry_uuid = data.get("entry_uuid")
        title = data.get("title")
        body = data.get("body")
        created_by = data.get("created_by")
        version_number = data.get("project_version_number")

        if not isinstance(entry_uuid, str):
            raise ValueError("Journal entry UUID is missing.")
        if not isinstance(title, str):
            raise ValueError("Journal title is missing.")
        if not isinstance(body, str):
            raise ValueError("Journal body is missing.")
        if not isinstance(created_by, str):
            raise ValueError("Journal author is missing.")
        if version_number is not None and (
            not isinstance(version_number, int)
            or isinstance(version_number, bool)
        ):
            raise ValueError("Journal project version is invalid.")

        return cls.create(
            entry_uuid=entry_uuid,
            title=title,
            body=body,
            created_by=created_by,
            created_at_utc=created_at,
            project_version_number=version_number,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(value: str, label: str, maximum_length: int) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{label} is required.")
    if len(normalized) > maximum_length:
        raise ValueError(
            f"{label} cannot exceed {maximum_length} characters."
        )

    return normalized
