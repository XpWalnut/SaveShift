from dataclasses import dataclass


@dataclass(frozen=True)
class PackageInfo:
    package_format_version: int
    game_id: str
    project_name: str
    created_at_utc: str
    created_by: str
    save_shift_version: str
    file_count: int
    verified: bool