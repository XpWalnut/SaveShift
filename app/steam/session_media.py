from dataclasses import asdict, dataclass
from datetime import datetime
import uuid


@dataclass(frozen=True)
class SteamSessionMediaReference:
    """Signed-index pointer to encrypted media for one exact save package."""

    project_uuid: str
    project_version: int
    package_item_id: str
    package_checksum: str
    media_item_id: str
    image_checksum: str
    key_epoch: int
    captured_at_utc: str

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> "SteamSessionMediaReference":
        if not isinstance(value, dict):
            raise ValueError("A Steam session-media reference must be an object.")
        try:
            reference = cls(
                project_uuid=str(uuid.UUID(str(value["project_uuid"]))),
                project_version=int(value["project_version"]),
                package_item_id=str(value["package_item_id"]),
                package_checksum=str(value["package_checksum"]).lower(),
                media_item_id=str(value["media_item_id"]),
                image_checksum=str(value["image_checksum"]).lower(),
                key_epoch=int(value["key_epoch"]),
                captured_at_utc=str(value["captured_at_utc"]),
            )
            reference.validate()
            return reference
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("The Steam session-media reference is invalid.") from error

    def validate(self) -> None:
        uuid.UUID(self.project_uuid)
        if self.project_version < 1 or self.key_epoch < 1:
            raise ValueError("The Steam session-media version is invalid.")
        self._item_id(self.package_item_id)
        self._item_id(self.media_item_id)
        self._checksum(self.package_checksum)
        self._checksum(self.image_checksum)
        timestamp = datetime.fromisoformat(self.captured_at_utc)
        if timestamp.tzinfo is None:
            raise ValueError("The Steam session-media timestamp needs a timezone.")

    def matches_package(
        self,
        *,
        project_uuid: str,
        project_version: int,
        package_item_id: str,
        package_checksum: str,
    ) -> bool:
        return (
            self.project_uuid == str(uuid.UUID(project_uuid))
            and self.project_version == project_version
            and self.package_item_id == self._item_id(package_item_id)
            and self.package_checksum == package_checksum.lower()
        )

    @staticmethod
    def _item_id(value: str) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("The Steam media Workshop item is invalid.")
        return normalized

    @staticmethod
    def _checksum(value: str) -> str:
        normalized = str(value).lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("The Steam session-media checksum is invalid.")
        return normalized
