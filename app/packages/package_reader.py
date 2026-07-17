from pathlib import Path
from zipfile import ZipFile
import json

from app.packages.package_info import PackageInfo
from app.packages.package_journal_entry import PackageJournalEntry
from app.packages.package_service import PackageService


class PackageReader:
    @staticmethod
    def read(package_path: Path, verify: bool = True) -> PackageInfo:
        if not package_path.exists():
            raise FileNotFoundError(f"Package does not exist: {package_path}")

        if verify:
            PackageService.verify_package(package_path)

        with ZipFile(package_path, "r") as package:
            package_names = set(package.namelist())

            if "manifest.json" not in package_names:
                raise ValueError("Package is missing manifest.json")

            if "checksums.json" not in package_names:
                raise ValueError("Package is missing checksums.json")

            manifest = json.loads(package.read("manifest.json"))

        journal_data = manifest.get("journal_entries", [])

        if not isinstance(journal_data, list):
            raise ValueError("Package journal_entries must be a list.")

        journal_entries = tuple(
            PackageJournalEntry.from_dict(entry)
            for entry in journal_data
        )

        return PackageInfo(
            package_format_version=manifest["package_format_version"],
            project_uuid=manifest["project_uuid"],
            project_version=manifest["project_version"],
            game_id=manifest["game_id"],
            project_name=manifest["project_name"],
            created_at_utc=manifest["created_at_utc"],
            created_by=manifest["created_by"],
            save_shift_version=manifest["save_shift_version"],
            file_count=len(manifest["files"]),
            verified=verify,
            journal_entries=journal_entries,
        )
