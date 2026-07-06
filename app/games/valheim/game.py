from pathlib import Path

from app.games.base import GameWorld, SupportedGame


class ValheimGame(SupportedGame):
    game_id = "valheim"
    display_name = "Valheim"
    process_names = ["valheim.exe"]

    def scan_worlds(self, save_path: Path) -> list[GameWorld]:
        worlds: list[GameWorld] = []

        if not save_path.exists():
            return worlds

        db_files = list(save_path.glob("*.db"))

        for db_file in db_files:
            world_name = db_file.stem
            fwl_file = save_path / f"{world_name}.fwl"

            files = [db_file]

            if fwl_file.exists():
                files.append(fwl_file)

            worlds.append(
                GameWorld(
                    name=world_name,
                    path=save_path,
                    files=files,
                )
            )

        return sorted(worlds, key=lambda world: world.name.lower())