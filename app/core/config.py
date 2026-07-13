import os
from pathlib import Path

from app.core.constants import AppResources


class AppConfig:
    @staticmethod
    def get_saveshift_directory() -> Path:
        return AppConfig._ensure_directory(
            Path.home() / AppResources.SAVESHIFT
        )

    @staticmethod
    def get_data_directory() -> Path:
        return AppConfig._ensure_directory(
            AppConfig.get_saveshift_directory() / AppResources.DATA
        )

    @staticmethod
    def get_logs_directory() -> Path:
        return AppConfig._ensure_directory(
            AppConfig.get_saveshift_directory() / AppResources.LOGS
        )

    @staticmethod
    def get_temp_directory() -> Path:
        return AppConfig._ensure_directory(
            AppConfig.get_saveshift_directory() / AppResources.TEMP
        )

    @staticmethod
    def get_backups_directory() -> Path:
        return AppConfig._ensure_directory(
            AppConfig.get_saveshift_directory() / AppResources.BACKUPS
        )

    @staticmethod
    def get_packages_directory() -> Path:
        return AppConfig._ensure_directory(
            AppConfig.get_saveshift_directory() / AppResources.PACKAGES
        )

    @staticmethod
    def get_database_path() -> Path:
        return AppConfig.get_data_directory() / AppResources.DATABASE_FILE

    @staticmethod
    def get_settings_path() -> Path:
        configured_path = os.environ.get("SAVESHIFT_SETTINGS_PATH")

        if configured_path:
            settings_path = Path(configured_path)
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            return settings_path

        return AppConfig.get_data_directory() / AppResources.SETTINGS_FILE

    @staticmethod
    def _ensure_directory(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path
