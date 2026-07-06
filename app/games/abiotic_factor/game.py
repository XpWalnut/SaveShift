from pathlib import Path

from app.games.base import GameWorld, SupportedGame


class AbioticFactorGame(SupportedGame):
    game_id = "abiotic_factor"
    display_name = "Abiotic Factor"
    process_names = ["AbioticFactor-Win64-Shipping.exe", "AbioticFactor.exe"]

    def scan_worlds(self, save_path: Path) -> list[GameWorld]:
        worlds: list[GameWorld] = []

        if not save_path.exists():
            return worlds

        for world_folder in save_path.iterdir():
            if not world_folder.is_dir():
                continue

            files = [path for path in world_folder.rglob("*") if path.is_file()]

            if not files:
                continue

            worlds.append(
                GameWorld(
                    name=world_folder.name,
                    path=world_folder,
                    files=files,
                )
            )

        return sorted(worlds, key=lambda world: world.name.lower())