from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PACKAGE_FORMAT_VERSION = 1


@dataclass(frozen=True)
class PackageManifest:
    package_format_version: int
    game_id: str
    project_name: str
    created_at_utc: str
    created_by: str
    save_shift_version: str
    files: list[str]
    metadata: dict[str, Any]

    @staticmethod
    def create(
        game_id: str,
        project_name: str,
        created_by: str,
        save_shift_version: str,
        files: list[Path],
        root_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> "PackageManifest":
        relative_files = [
            str(file.relative_to(root_path)).replace("\\", "/")
            for file in files
        ]

        return PackageManifest(
            package_format_version=PACKAGE_FORMAT_VERSION,
            game_id=game_id,
            project_name=project_name,
            created_at_utc=datetime.now(UTC).isoformat(),
            created_by=created_by,
            save_shift_version=save_shift_version,
            files=relative_files,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)