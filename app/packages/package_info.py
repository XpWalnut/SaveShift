from dataclasses import dataclass, field

from app.packages.package_journal_entry import PackageJournalEntry
from app.packages.package_metadata import PackageMetadata


@dataclass(frozen=True)
class PackageInfo:
    package_format_version: int
    project_uuid: str
    project_version: int
    game_id: str
    project_name: str
    created_at_utc: str
    created_by: str
    save_shift_version: str
    file_count: int
    verified: bool
    metadata: PackageMetadata = field(default_factory=PackageMetadata)
    journal_entries: tuple[PackageJournalEntry, ...] = ()
