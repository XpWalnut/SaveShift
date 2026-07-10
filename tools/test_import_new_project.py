from pathlib import Path

from app.database.repositories.project_repository import ProjectRepository
from app.services.import_service import ImportService
from app.services.project_version_service import ProjectVersionService


def main() -> None:
    package_path = Path(input("Package path: ").strip().strip('"'))

    package_info = ImportService.read_package_for_test(package_path)

    existing_project = ProjectRepository.get_by_uuid(package_info.project_uuid)

    if existing_project is not None:
        print("A local project with this UUID already exists.")
        print(f"Project: {existing_project.name}")
        print(f"Path: {existing_project.local_path}")
        print()
        print("This test is meant for packages that do NOT already exist locally.")
        return

    version = ImportService.import_package(
        package_path=package_path,
        imported_by="Jake",
        notes="Test import creating a brand-new project",
    )

    project = ProjectRepository.get_by_id(version.project_id)
    latest = ProjectVersionService.get_latest_version(version.project_id)

    print("Imported new project successfully.")
    print()
    print(f"Project: {project.name if project else 'Unknown'}")
    print(f"Project ID: {version.project_id}")
    print(f"Project path: {project.local_path if project else 'Unknown'}")
    print(f"Version: {version.version_number}")
    print(f"Source: {version.source_type}")
    print(f"Latest version: {latest.version_number if latest else 'Unknown'}")
    print(f"Package: {version.package_path}")


if __name__ == "__main__":
    main()