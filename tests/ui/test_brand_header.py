from app.ui.widgets.brand_header import BrandHeader


def test_refined_header_crops_wordmark_from_lower_artwork() -> None:
    source = BrandHeader._wordmark_source_rect(1254, 1254)

    assert source.x() > 0
    assert source.y() > 1254 // 2
    assert source.width() > source.height() * 4


def test_refined_header_stays_compact_at_different_widths(qtbot) -> None:
    header = BrandHeader()
    qtbot.addWidget(header)
    header.show()

    header.resize(950, header.height())
    qtbot.wait(10)
    compact_height = header.height()
    header.resize(1920, header.height())
    qtbot.wait(10)

    assert compact_height == 92
    assert header.height() == 92
