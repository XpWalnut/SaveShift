import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


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


def test_branding_source_artwork_dimensions() -> None:
    assert _png_dimensions(ROOT / "assets/icons/SaveShift.png") == (1254, 1254)
    assert _png_dimensions(ROOT / "assets/steam/SaveShift-Banner.png") == (1834, 857)


def test_windows_icon_contains_required_sizes() -> None:
    assert _ico_dimensions(ROOT / "assets/icons/SaveShift.ico") == {
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    }
