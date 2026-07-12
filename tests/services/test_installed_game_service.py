from pathlib import Path

import pytest

from app.games.game_id import GameId
from app.services.installed_game_service import InstalledGameService


def test_duplicate_installed_game_is_rejected(
    temp_save_root: Path,
) -> None:
    InstalledGameService.add_installed_game(
        game_id=GameId.ABIOTIC_FACTOR,
        display_name="Abiotic Factor",
        save_path=str(temp_save_root),
    )

    with pytest.raises(
        ValueError,
        match="Abiotic Factor has already been configured",
    ):
        InstalledGameService.add_installed_game(
            game_id=GameId.ABIOTIC_FACTOR,
            display_name="Abiotic Factor",
            save_path=str(temp_save_root),
        )

    installed_games = InstalledGameService.get_installed_games()

    assert len(installed_games) == 1
    assert installed_games[0].game_id == GameId.ABIOTIC_FACTOR.value