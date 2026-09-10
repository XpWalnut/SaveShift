from dataclasses import dataclass
import json
from pathlib import Path

from app.core.config import AppConfig
from app.core.logging import logger
from app.core.secrets import SecretProtectionError, SecretProtector


@dataclass(frozen=True)
class AppSettings:
    automatic_update_checks: bool = True
    manual_transfer_controls: bool = False
    player_display_name: str = ""
    coordination_enabled: bool = False
    coordination_server_url: str = ""
    coordination_device_id: str = ""
    coordination_device_name: str = ""
    coordination_device_token: str = ""
    coordination_is_administrator: bool = False
    coordination_provider_kind: str = ""
    coordination_cloudflare_account_id: str = ""
    coordination_cloudflare_script_name: str = ""


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

        if not isinstance(data, dict):
            logger.warning("Ignoring invalid settings object in %s.", path)
            return AppSettings()

        automatic_update_checks = SettingsService._boolean(
            data,
            "automatic_update_checks",
            True,
            path,
        )
        coordination_enabled = SettingsService._boolean(
            data,
            "coordination_enabled",
            False,
            path,
        )
        manual_transfer_controls = SettingsService._boolean(
            data,
            "manual_transfer_controls",
            False,
            path,
        )
        coordination_is_administrator = SettingsService._boolean(
            data,
            "coordination_is_administrator",
            False,
            path,
        )
        protected_token = SettingsService._string(
            data,
            "coordination_device_token_protected",
        )
        device_token = ""

        if protected_token:
            try:
                device_token = SecretProtector.unprotect(protected_token)
            except SecretProtectionError as error:
                logger.warning(
                    "Could not unlock coordination credential in %s: %s",
                    path,
                    error,
                )

        return AppSettings(
            automatic_update_checks=automatic_update_checks,
            manual_transfer_controls=manual_transfer_controls,
            player_display_name=SettingsService._string(
                data,
                "player_display_name",
            ),
            coordination_enabled=coordination_enabled,
            coordination_server_url=SettingsService._string(
                data,
                "coordination_server_url",
            ),
            coordination_device_id=SettingsService._string(
                data,
                "coordination_device_id",
            ),
            coordination_device_name=SettingsService._string(
                data,
                "coordination_device_name",
            ),
            coordination_device_token=device_token,
            coordination_is_administrator=coordination_is_administrator,
            coordination_provider_kind=SettingsService._string(
                data,
                "coordination_provider_kind",
            ),
            coordination_cloudflare_account_id=SettingsService._string(
                data,
                "coordination_cloudflare_account_id",
            ),
            coordination_cloudflare_script_name=SettingsService._string(
                data,
                "coordination_cloudflare_script_name",
            ),
        )

    @staticmethod
    def save(
        settings: AppSettings,
        settings_path: Path | None = None,
    ) -> None:
        path = settings_path or AppConfig.get_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        protected_token = (
            SecretProtector.protect(settings.coordination_device_token)
            if settings.coordination_device_token
            else ""
        )
        data = {
            "automatic_update_checks": settings.automatic_update_checks,
            "manual_transfer_controls": settings.manual_transfer_controls,
            "player_display_name": settings.player_display_name,
            "coordination_enabled": settings.coordination_enabled,
            "coordination_server_url": settings.coordination_server_url,
            "coordination_device_id": settings.coordination_device_id,
            "coordination_device_name": settings.coordination_device_name,
            "coordination_device_token_protected": protected_token,
            "coordination_is_administrator": settings.coordination_is_administrator,
            "coordination_provider_kind": settings.coordination_provider_kind,
            "coordination_cloudflare_account_id": (
                settings.coordination_cloudflare_account_id
            ),
            "coordination_cloudflare_script_name": (
                settings.coordination_cloudflare_script_name
            ),
        }
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)

    @staticmethod
    def _boolean(
        data: dict[str, object],
        key: str,
        default: bool,
        path: Path,
    ) -> bool:
        value = data.get(key, default)

        if isinstance(value, bool):
            return value

        logger.warning("Ignoring invalid %s value in %s.", key, path)
        return default

    @staticmethod
    def _string(data: dict[str, object], key: str) -> str:
        value = data.get(key, "")
        return value if isinstance(value, str) else ""
