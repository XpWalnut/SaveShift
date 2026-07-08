from pathlib import Path

from app.database.repositories.project_repository import ProjectRepository
from app.services.import_service import ImportService
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.services.project_version_service import ProjectVersionService


def main() -> None:
    installed_games = InstalledGameService.get_installed_games()

    if not installed_games:
        print("No installed games configured.")
        return

    installed_game = installed_games[0]
    projects = ProjectService.get_projects_for_installed_game(installed_game.id)

    if not projects:
        print("No projects discovered.")
        return

    project = projects[0]
    latest = ProjectVersionService.get_latest_version(project.id)

    print(f"Project: {project.name}")
    print(f"Current local version: {latest.version_number if latest else 'None'}")
    print()

    package_path = Path(input("Package path to import: ").strip().strip('"'))

    try:
        version = ImportService.import_package(
            package_path=package_path,
            imported_by="Jake",
            notes="Version-aware import test",
        )
    except Exception as error:
        print("Import rejected:")
        print(error)
        return

    print("Import accepted:")
    print(f"Imported version: {version.version_number}")
    print(f"Source: {version.source_type}")
    print(f"Backup: {version.backup_path}")


if __name__ == "__main__":
    main()