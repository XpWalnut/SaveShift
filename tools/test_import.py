from pathlib import Path

from app.services.import_service import ImportService


def main() -> None:
    package_path = Path(input("Package path: ").strip().strip('"'))

    version = ImportService.import_package(
        package_path=package_path,
        imported_by="Jake",
        notes="Test import from tools/test_import.py",
    )

    print("Imported package:")
    print(f"Project ID: {version.project_id}")
    print(f"Version: {version.version_number}")
    print(f"Created by: {version.created_by}")
    print(f"Source: {version.source_type}")
    print(f"Package: {version.package_path}")
    print(f"Backup: {version.backup_path}")


if __name__ == "__main__":
    main()