from app.services.hosting_service import HostingService
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService


def main() -> None:
    installed_games = InstalledGameService.get_installed_games()

    if not installed_games:
        print("No installed games configured.")
        return

    installed_game = installed_games[0]

    print(f"Using installed game: {installed_game.display_name}")
    print(f"Save path: {installed_game.save_path}")

    projects = ProjectService.get_projects_for_installed_game(installed_game.id)

    if not projects:
        print("No projects found. Discover projects first.")
        return

    project = projects[0]

    print(f"Hosting project: {project.name}")

    version = HostingService.host_project(
        project_id=project.id,
        game_id=installed_game.game_id,
        hosted_by="Jake",
        notes="Test hosted version from tools/test_hosting.py",
    )

    print()
    print("Hosted version created:")
    print(f"Project ID: {version.project_id}")
    print(f"Version: {version.version_number}")
    print(f"Created by: {version.created_by}")
    print(f"Source: {version.source_type}")
    print(f"Package: {version.package_path}")
    print(f"Checksum: {version.package_checksum}")


if __name__ == "__main__":
    main()