import pytest

from app.ui.widgets.brand_header import BrandHeader


def test_hero_cover_crop_preserves_source_aspect_ratio() -> None:
    source = BrandHeader._cover_source_rect(3840, 1240, 1180, 197)

    assert source.width() / source.height() == pytest.approx(1180 / 197, rel=0.002)
    assert source.x() == 0
    assert source.y() > 0


def test_hero_height_grows_without_becoming_a_thin_fullscreen_strip(qtbot) -> None:
    header = BrandHeader()
    qtbot.addWidget(header)
    header.show()

    header.resize(950, header.height())
    qtbot.wait(10)
    compact_height = header.height()
    header.resize(1920, header.height())
    qtbot.wait(10)

    assert compact_height == 158
    assert header.height() == 224
