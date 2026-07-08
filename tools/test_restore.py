from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.services.project_version_service import ProjectVersionService
from app.services.restore_service import RestoreService


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
    versions = ProjectVersionService.get_versions_for_project(project.id)

    if not versions:
        print("No versions found for project.")
        return

    print(f"Project: {project.name}")
    print()

    for index, version in enumerate(versions, start=1):
        print(
            f"{index}. Version {version.version_number} "
            f"[{version.source_type}] "
            f"by {version.created_by}"
        )

    print()

    selection = int(input("Choose version to restore: ").strip())
    selected_version = versions[selection - 1]

    RestoreService.restore(selected_version)

    print()
    print(f"Restored Version {selected_version.version_number}.")


if __name__ == "__main__":
    main()