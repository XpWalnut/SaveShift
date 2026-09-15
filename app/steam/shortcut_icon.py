import ctypes
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths

from app.core.logging import logger
from app.core.resources import get_resource_path
from app.steam.constants import SAVESHIFT_STEAM_APP_ID


def repair_steam_desktop_shortcut_icon(
    *,
    desktop_directory: Path | None = None,
    icon_path: Path | None = None,
    force: bool = False,
) -> int:
    """Point Steam-created Save Shift URL shortcuts at the bundled icon."""
    if not force and (sys.platform != "win32" or not getattr(sys, "frozen", False)):
        return 0
    desktop = desktop_directory or Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    )
    icon = (icon_path or get_resource_path(
        "assets/icons/SaveShift-Vaporwave.ico"
    )).resolve()
    if not desktop.is_dir() or not icon.is_file():
        return 0

    target = f"steam://rungameid/{SAVESHIFT_STEAM_APP_ID}".casefold()
    repaired = 0
    for shortcut in desktop.glob("*.url"):
        try:
            original = shortcut.read_text(encoding="utf-8-sig")
            lines = original.splitlines()
            if not any(
                line.partition("=")[0].strip().casefold() == "url"
                and line.partition("=")[2].strip().casefold() == target
                for line in lines
            ):
                continue
            replacement = _replace_icon(lines, icon)
            updated = "\n".join(replacement) + "\n"
            if updated == original.replace("\r\n", "\n"):
                continue
            temporary = shortcut.with_suffix(".url.tmp")
            temporary.write_text(updated, encoding="utf-8")
            temporary.replace(shortcut)
            repaired += 1
        except OSError as error:
            logger.warning(
                "Could not repair Steam shortcut icon path=%s: %s",
                shortcut,
                error,
            )
    if repaired:
        _refresh_windows_icons()
        logger.info("Repaired %s Steam desktop shortcut icon(s).", repaired)
    return repaired


def _replace_icon(lines: list[str], icon_path: Path) -> list[str]:
    icon_value = f"IconFile={icon_path}"
    found_icon = False
    found_index = False
    result: list[str] = []
    for line in lines:
        key = line.partition("=")[0].strip().casefold()
        if key == "iconfile":
            result.append(icon_value)
            found_icon = True
        elif key == "iconindex":
            result.append("IconIndex=0")
            found_index = True
        else:
            result.append(line)
    if not found_icon:
        result.append(icon_value)
    if not found_index:
        result.append("IconIndex=0")
    return result


def _refresh_windows_icons() -> None:
    try:
        # SHCNE_ASSOCCHANGED / SHCNF_IDLIST: refresh Explorer's icon cache.
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except (AttributeError, OSError):
        pass
