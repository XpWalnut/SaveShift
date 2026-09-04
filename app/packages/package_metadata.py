from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PackageMetadata:
    source_device_name: str | None = None
    lineage_name: str = "main"
    parent_project_version: int | None = None
    parent_package_checksum: str | None = None
    notes: str | None = None
    game_metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(value: object) -> "PackageMetadata":
        if value is None:
            return PackageMetadata()

        if not isinstance(value, dict):
            raise ValueError("Package metadata must be an object.")

        source_device_name = _optional_string(
            value,
            "source_device_name",
        )
        lineage_name = value.get("lineage_name", "main")

        if (
            not isinstance(lineage_name, str)
            or not lineage_name.strip()
            or len(lineage_name.strip()) > 100
        ):
            raise ValueError("Package metadata lineage_name must be text.")

        parent_project_version = value.get("parent_project_version")

        if (
            parent_project_version is not None
            and (
                isinstance(parent_project_version, bool)
                or not isinstance(parent_project_version, int)
                or parent_project_version < 1
            )
        ):
            raise ValueError(
                "Package metadata parent_project_version must be a "
                "positive integer."
            )

        parent_package_checksum = _optional_string(
            value,
            "parent_package_checksum",
        )

        if (
            parent_package_checksum is not None
            and (
                len(parent_package_checksum) != 64
                or any(
                    character not in "0123456789abcdefABCDEF"
                    for character in parent_package_checksum
                )
            )
        ):
            raise ValueError(
                "Package metadata parent_package_checksum must be a "
                "SHA-256 checksum."
            )

        notes = _optional_string(value, "notes")
        game_metadata = value.get("game_metadata", {})

        if not isinstance(game_metadata, dict):
            raise ValueError("Package metadata game_metadata must be an object.")

        return PackageMetadata(
            source_device_name=source_device_name,
            lineage_name=lineage_name.strip(),
            parent_project_version=parent_project_version,
            parent_package_checksum=(
                parent_package_checksum.lower()
                if parent_package_checksum is not None
                else None
            ),
            notes=notes,
            game_metadata=dict(game_metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_string(
    data: dict[str, Any],
    key: str,
) -> str | None:
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"Package metadata {key} must be text.")

    stripped = value.strip()
    return stripped or None
