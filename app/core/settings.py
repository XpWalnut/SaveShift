from dataclasses import asdict, dataclass
import json
from pathlib import Path

from app.core.config import AppConfig
from app.core.logging import logger


@dataclass(frozen=True)
class AppSettings:
    automatic_update_checks: bool = True


class SettingsService:
    @staticmethod
    def load(settings_path: Path | None = None) -> AppSettings:
        path = settings_path or AppConfig.get_settings_path()

        if not path.exists():
            return AppSettings()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Could not load settings from %s: %s", path, error)
            return AppSettings()

        automatic_update_checks = data.get("automatic_update_checks", True)

        if not isinstance(automatic_update_checks, bool):
            logger.warning(
                "Ignoring invalid automatic_update_checks value in %s.",
                path,
            )
            automatic_update_checks = True

        return AppSettings(
            automatic_update_checks=automatic_update_checks,
        )

    @staticmethod
    def save(
        settings: AppSettings,
        settings_path: Path | None = None,
    ) -> None:
        path = settings_path or AppConfig.get_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(asdict(settings), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
