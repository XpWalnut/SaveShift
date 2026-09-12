import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def _png_color_type(path: Path) -> int:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return data[25]


def _ico_dimensions(path: Path) -> set[tuple[int, int]]:
    data = path.read_bytes()
    reserved, image_type, image_count = struct.unpack_from("<HHH", data)
    assert reserved == 0
    assert image_type == 1

    dimensions: set[tuple[int, int]] = set()
    for index in range(image_count):
        width, height = struct.unpack_from("BB", data, 6 + (index * 16))
        dimensions.add((width or 256, height or 256))
    return dimensions


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:2] == b"\xff\xd8"
    offset = 2
    start_of_frame_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while offset < len(data):
        assert data[offset] == 0xFF
        while data[offset] == 0xFF:
            offset += 1
        marker = data[offset]
        offset += 1
        segment_length = struct.unpack_from(">H", data, offset)[0]
        if marker in start_of_frame_markers:
            height, width = struct.unpack_from(">HH", data, offset + 3)
            return width, height
        offset += segment_length
    raise AssertionError("JPEG has no start-of-frame marker")


def test_branding_source_artwork_dimensions() -> None:
    assert _png_dimensions(ROOT / "assets/icons/SaveShift.png") == (1254, 1254)
    assert _png_dimensions(ROOT / "assets/steam/SaveShift-Banner.png") == (1834, 857)
    assert _png_dimensions(ROOT / "assets/ui/SaveShift-Wordmark.png") == (
        2155,
        730,
    )
    assert _png_color_type(ROOT / "assets/ui/SaveShift-Wordmark.png") == 6


def test_steam_ready_artwork_dimensions() -> None:
    steam_assets = ROOT / "assets/steam"
    assert _png_dimensions(steam_assets / "SaveShift-ShortcutIcon-512.png") == (
        512,
        512,
    )
    assert _jpeg_dimensions(steam_assets / "SaveShift-AppIcon-184.jpg") == (184, 184)
    assert _png_dimensions(steam_assets / "SaveShift-Header-920x430.png") == (
        920,
        430,
    )
    assert _png_dimensions(
        steam_assets / "SaveShift-LibraryHero-3840x1240.png"
    ) == (3840, 1240)
    library_logo = steam_assets / "SaveShift-LibraryLogo-1280x720.png"
    assert _png_dimensions(library_logo) == (1280, 720)
    assert _png_color_type(library_logo) == 6


def test_windows_icon_contains_required_sizes() -> None:
    required_sizes = {
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    }
    assert _ico_dimensions(ROOT / "assets/icons/SaveShift.ico") == required_sizes
    assert _ico_dimensions(
        ROOT / "assets/icons/SaveShift-Vaporwave.ico"
    ) == required_sizes


def test_build_and_installer_use_vaporwave_icon_and_header_assets() -> None:
    spec = (ROOT / "SaveShift.spec").read_text(encoding="utf-8")
    installer = (ROOT / "installer/SaveShift.iss").read_text(encoding="utf-8")

    assert "assets/icons/SaveShift-Vaporwave.ico" in spec
    assert "assets/steam/SaveShift-LibraryHero-3840x1240.png" in spec
    assert "assets/ui/SaveShift-Wordmark.png" in spec
    assert "SaveShift-Vaporwave.ico" in installer
