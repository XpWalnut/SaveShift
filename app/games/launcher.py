import csv
import os
import subprocess


class GameLauncher:
    @staticmethod
    def launch_steam_game(steam_app_id: int) -> None:
        uri = f"steam://rungameid/{steam_app_id}"

        try:
            os.startfile(uri)
        except OSError as error:
            raise RuntimeError(
                "Windows could not open Steam. "
                "Make sure Steam is installed and try again."
            ) from error

    @staticmethod
    def is_any_process_running(process_names: list[str]) -> bool:
        normalized_names = {
            process_name.casefold()
            for process_name in process_names
        }

        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return False

        running_processes = {
            row[0].casefold()
            for row in csv.reader(result.stdout.splitlines())
            if row
        }

        return bool(normalized_names & running_processes)