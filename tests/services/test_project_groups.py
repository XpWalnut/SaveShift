from pathlib import Path

from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.database.repositories.project_repository import ProjectRepository


def test_project_group_associations_are_persisted_and_queryable(
    tmp_path: Path,
) -> None:
    game = InstalledGameRepository.add(
        game_id="valheim",
        display_name="Valheim",
        save_path=str(tmp_path),
    )
    first = ProjectRepository.create(
        installed_game_id=game.id,
        project_uuid="11111111-1111-4111-8111-111111111111",
        name="First",
        local_path=tmp_path / "First",
    )
    second = ProjectRepository.create(
        installed_game_id=game.id,
        project_uuid="22222222-2222-4222-8222-222222222222",
        name="Second",
        local_path=tmp_path / "Second",
    )

    ProjectRepository.associate_group(first.id, "family")
    assert [project.uuid for project in ProjectRepository.get_for_group("family")] == [
        first.uuid
    ]

    assert ProjectRepository.associate_unassigned("friends") == 1
    assert ProjectRepository.get_by_id(second.id).coordination_group_id == "friends"

    ProjectRepository.associate_group(first.id, None)
    assert ProjectRepository.get_for_group("family") == []
