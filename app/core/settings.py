from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import uuid

from app.core.config import AppConfig
from app.core.logging import logger
from app.core.secrets import SecretProtectionError, SecretProtector


@dataclass(frozen=True)
class CoordinationGroupSettings:
    group_id: str
    name: str
    server_url: str = ""
    device_id: str = ""
    device_name: str = ""
    device_token: str = ""
    is_administrator: bool = False
    provider_kind: str = ""
    cloudflare_account_id: str = ""
    cloudflare_script_name: str = ""
    steam_manifest_item_id: str = ""
    steam_package_index_item_id: str = ""
    steam_administrator_steam_id: str = ""


@dataclass(frozen=True)
class AppSettings:
    automatic_update_checks: bool = True
    manual_transfer_controls: bool = False
    prompt_for_session_journal: bool = True
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
    coordination_groups: tuple[CoordinationGroupSettings, ...] = ()
    active_coordination_group_id: str = ""
    legacy_group_migration_pending: bool = field(
        default=False,
        compare=False,
        repr=False,
    )

    @property
    def active_coordination_group(self) -> CoordinationGroupSettings | None:
        return next(
            (
                group
                for group in self.coordination_groups
                if group.group_id == self.active_coordination_group_id
            ),
            None,
        )

    def with_active_group(self, group_id: str) -> "AppSettings":
        group = next(
            (item for item in self.coordination_groups if item.group_id == group_id),
            None,
        )
        if group is None:
            raise ValueError(f"Coordination group not found: {group_id}")
        return self._with_group_mirror(group)

    def upsert_group(
        self,
        group: CoordinationGroupSettings,
        *,
        make_active: bool = True,
    ) -> "AppSettings":
        groups = tuple(
            group if item.group_id == group.group_id else item
            for item in self.coordination_groups
        )
        if not any(item.group_id == group.group_id for item in groups):
            groups += (group,)
        updated = replace(self, coordination_groups=groups)
        return updated._with_group_mirror(group) if make_active else updated

    def without_group(self, group_id: str) -> "AppSettings":
        groups = tuple(
            group for group in self.coordination_groups if group.group_id != group_id
        )
        updated = replace(self, coordination_groups=groups)
        if groups:
            return updated._with_group_mirror(groups[0])
        return replace(
            updated,
            active_coordination_group_id="",
            coordination_enabled=False,
            coordination_server_url="",
            coordination_device_id="",
            coordination_device_name="",
            coordination_device_token="",
            coordination_is_administrator=False,
            coordination_provider_kind="",
            coordination_cloudflare_account_id="",
            coordination_cloudflare_script_name="",
        )

    def rename_group(self, group_id: str, name: str) -> "AppSettings":
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Group name cannot be empty.")
        group = next(
            (item for item in self.coordination_groups if item.group_id == group_id),
            None,
        )
        if group is None:
            raise ValueError(f"Coordination group not found: {group_id}")
        return self.upsert_group(
            replace(group, name=normalized_name),
            make_active=group_id == self.active_coordination_group_id,
        )

    def _with_group_mirror(
        self,
        group: CoordinationGroupSettings,
    ) -> "AppSettings":
        return replace(
            self,
            active_coordination_group_id=group.group_id,
            coordination_enabled=True,
            coordination_server_url=group.server_url,
            coordination_device_id=group.device_id,
            coordination_device_name=group.device_name,
            coordination_device_token=group.device_token,
            coordination_is_administrator=group.is_administrator,
            coordination_provider_kind=group.provider_kind,
            coordination_cloudflare_account_id=group.cloudflare_account_id,
            coordination_cloudflare_script_name=group.cloudflare_script_name,
            legacy_group_migration_pending=False,
        )


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
        prompt_for_session_journal = SettingsService._boolean(
            data,
            "prompt_for_session_journal",
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

        groups = SettingsService._groups(data, path)
        active_group_id = SettingsService._string(
            data,
            "active_coordination_group_id",
        )
        migrated_legacy = False
        if "coordination_groups" not in data and coordination_enabled:
            legacy_url = SettingsService._string(data, "coordination_server_url")
            legacy_device_id = SettingsService._string(data, "coordination_device_id")
            if legacy_url and legacy_device_id:
                group_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{legacy_url.rstrip('/')}|{legacy_device_id}",
                    )
                )
                script_name = SettingsService._string(
                    data,
                    "coordination_cloudflare_script_name",
                )
                groups = (
                    CoordinationGroupSettings(
                        group_id=group_id,
                        name=script_name or "Original group",
                        server_url=legacy_url,
                        device_id=legacy_device_id,
                        device_name=SettingsService._string(
                            data,
                            "coordination_device_name",
                        ),
                        device_token=device_token,
                        is_administrator=coordination_is_administrator,
                        provider_kind=SettingsService._string(
                            data,
                            "coordination_provider_kind",
                        ),
                        cloudflare_account_id=SettingsService._string(
                            data,
                            "coordination_cloudflare_account_id",
                        ),
                        cloudflare_script_name=script_name,
                    ),
                )
                active_group_id = group_id
                migrated_legacy = True

        if groups and not any(group.group_id == active_group_id for group in groups):
            active_group_id = groups[0].group_id

        settings = AppSettings(
            automatic_update_checks=automatic_update_checks,
            manual_transfer_controls=manual_transfer_controls,
            prompt_for_session_journal=prompt_for_session_journal,
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
            coordination_groups=groups,
            active_coordination_group_id=active_group_id,
            legacy_group_migration_pending=migrated_legacy,
        )
        active_group = settings.active_coordination_group
        if active_group is not None:
            settings = settings._with_group_mirror(active_group)
            settings = replace(
                settings,
                coordination_enabled=coordination_enabled,
            )
        return replace(
            settings,
            legacy_group_migration_pending=migrated_legacy,
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
            "prompt_for_session_journal": settings.prompt_for_session_journal,
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
            "active_coordination_group_id": (
                settings.active_coordination_group_id
            ),
            "coordination_groups": [
                SettingsService._serialize_group(group)
                for group in settings.coordination_groups
            ],
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

    @staticmethod
    def _groups(
        data: dict[str, object],
        path: Path,
    ) -> tuple[CoordinationGroupSettings, ...]:
        raw_groups = data.get("coordination_groups", [])
        if not isinstance(raw_groups, list):
            logger.warning("Ignoring invalid coordination_groups value in %s.", path)
            return ()

        groups: list[CoordinationGroupSettings] = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                continue
            group_id = SettingsService._string(raw_group, "group_id")
            name = SettingsService._string(raw_group, "name")
            if not group_id or not name:
                continue
            if name.lower().startswith("saveshift-coordination-"):
                name = "My Save Shift Group"
            token = ""
            protected = SettingsService._string(
                raw_group,
                "device_token_protected",
            )
            if protected:
                try:
                    token = SecretProtector.unprotect(protected)
                except SecretProtectionError as error:
                    logger.warning(
                        "Could not unlock a coordination group credential in %s: %s",
                        path,
                        error,
                    )
            groups.append(
                CoordinationGroupSettings(
                    group_id=group_id,
                    name=name,
                    server_url=SettingsService._string(raw_group, "server_url"),
                    device_id=SettingsService._string(raw_group, "device_id"),
                    device_name=SettingsService._string(raw_group, "device_name"),
                    device_token=token,
                    is_administrator=SettingsService._boolean(
                        raw_group,
                        "is_administrator",
                        False,
                        path,
                    ),
                    provider_kind=SettingsService._string(
                        raw_group,
                        "provider_kind",
                    ),
                    cloudflare_account_id=SettingsService._string(
                        raw_group,
                        "cloudflare_account_id",
                    ),
                    cloudflare_script_name=SettingsService._string(
                        raw_group,
                        "cloudflare_script_name",
                    ),
                    steam_manifest_item_id=SettingsService._string(
                        raw_group,
                        "steam_manifest_item_id",
                    ),
                    steam_package_index_item_id=SettingsService._string(
                        raw_group,
                        "steam_package_index_item_id",
                    ),
                    steam_administrator_steam_id=SettingsService._string(
                        raw_group,
                        "steam_administrator_steam_id",
                    ),
                )
            )
        return tuple(groups)

    @staticmethod
    def _serialize_group(group: CoordinationGroupSettings) -> dict[str, object]:
        protected_token = (
            SecretProtector.protect(group.device_token)
            if group.device_token
            else ""
        )
        return {
            "group_id": group.group_id,
            "name": group.name,
            "server_url": group.server_url,
            "device_id": group.device_id,
            "device_name": group.device_name,
            "device_token_protected": protected_token,
            "is_administrator": group.is_administrator,
            "provider_kind": group.provider_kind,
            "cloudflare_account_id": group.cloudflare_account_id,
            "cloudflare_script_name": group.cloudflare_script_name,
            "steam_manifest_item_id": group.steam_manifest_item_id,
            "steam_package_index_item_id": group.steam_package_index_item_id,
            "steam_administrator_steam_id": group.steam_administrator_steam_id,
        }
