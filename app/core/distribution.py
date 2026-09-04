from __future__ import annotations

from enum import StrEnum
import os
from pathlib import Path
import sys
from collections.abc import Mapping

from app.steam.constants import SAVESHIFT_STEAM_APP_ID


class DistributionChannel(StrEnum):
    DEVELOPMENT = "development"
    STANDALONE = "standalone"
    STEAM = "steam"

    @property
    def updates_managed_externally(self) -> bool:
        return self is DistributionChannel.STEAM


DISTRIBUTION_MARKER_NAME = "saveshift-distribution.txt"


def detect_distribution_channel(
    *,
    executable_path: Path | None = None,
    frozen: bool | None = None,
    environ: Mapping[str, str] | None = None,
) -> DistributionChannel:
    environment = os.environ if environ is None else environ
    override = environment.get("SAVESHIFT_DISTRIBUTION_CHANNEL", "").strip()

    if override:
        try:
            return DistributionChannel(override.casefold())
        except ValueError:
            pass

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen

    if not is_frozen:
        return DistributionChannel.DEVELOPMENT

    executable = Path(sys.executable) if executable_path is None else executable_path
    marker_path = executable.resolve().parent / DISTRIBUTION_MARKER_NAME

    try:
        marker = marker_path.read_text(encoding="utf-8").strip().casefold()
    except OSError:
        marker = ""

    if marker == DistributionChannel.STEAM:
        return DistributionChannel.STEAM

    steam_app_id = environment.get("SteamAppId") or environment.get("SteamGameId")
    if steam_app_id == str(SAVESHIFT_STEAM_APP_ID):
        return DistributionChannel.STEAM

    return DistributionChannel.STANDALONE
