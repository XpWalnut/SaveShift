from pathlib import Path

from app.core.distribution import (
    DISTRIBUTION_MARKER_NAME,
    DistributionChannel,
    detect_distribution_channel,
)
from app.steam.constants import SAVESHIFT_STEAM_APP_ID


def test_source_checkout_is_development() -> None:
    assert (
        detect_distribution_channel(frozen=False, environ={})
        is DistributionChannel.DEVELOPMENT
    )


def test_frozen_build_defaults_to_standalone(tmp_path: Path) -> None:
    assert (
        detect_distribution_channel(
            executable_path=tmp_path / "SaveShift.exe",
            frozen=True,
            environ={},
        )
        is DistributionChannel.STANDALONE
    )


def test_steam_upload_marker_identifies_steam_build(tmp_path: Path) -> None:
    (tmp_path / DISTRIBUTION_MARKER_NAME).write_text("steam\n", encoding="utf-8")

    assert (
        detect_distribution_channel(
            executable_path=tmp_path / "SaveShift.exe",
            frozen=True,
            environ={},
        )
        is DistributionChannel.STEAM
    )


def test_steam_launch_environment_is_a_marker_fallback(tmp_path: Path) -> None:
    assert (
        detect_distribution_channel(
            executable_path=tmp_path / "SaveShift.exe",
            frozen=True,
            environ={"SteamAppId": str(SAVESHIFT_STEAM_APP_ID)},
        )
        is DistributionChannel.STEAM
    )


def test_explicit_channel_override_supports_packaging_tests(tmp_path: Path) -> None:
    assert (
        detect_distribution_channel(
            executable_path=tmp_path / "SaveShift.exe",
            frozen=True,
            environ={"SAVESHIFT_DISTRIBUTION_CHANNEL": "standalone"},
        )
        is DistributionChannel.STANDALONE
    )
