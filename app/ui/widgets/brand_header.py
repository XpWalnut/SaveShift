from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.core.resources import get_resource_path
from app.ui import theme


class BrandHeader(QWidget):
    """Responsive vaporwave hero with the Save Shift wordmark."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BrandHeader")
        self.setMinimumHeight(132)
        self.setMaximumHeight(224)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._hero = QPixmap(
            str(
                get_resource_path(
                    "assets/steam/SaveShift-LibraryHero-3840x1240.png"
                )
            )
        )
        self._wordmark = QPixmap(
            str(get_resource_path("assets/ui/SaveShift-Wordmark.png"))
        )
        self._update_responsive_height()

    @property
    def assets_available(self) -> bool:
        return not self._hero.isNull() and not self._wordmark.isNull()

    def resizeEvent(self, event) -> None:
        self._update_responsive_height()
        super().resizeEvent(event)

    def _update_responsive_height(self) -> None:
        # Grow modestly on wide windows without allowing the hero to dominate
        # the application or collapse into a thin panoramic strip.
        target = max(132, min(224, round(self.width() / 6)))
        if self.height() != target:
            self.setFixedHeight(target)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor(theme.WINDOW_BACKGROUND))

        if not self._hero.isNull():
            source = self._cover_source_rect(
                self._hero.width(),
                self._hero.height(),
                self.width(),
                self.height(),
            )
            painter.drawPixmap(
                self.rect(),
                self._hero,
                source,
            )

        painter.fillRect(self.rect(), QColor(4, 3, 22, 42))

        if not self._wordmark.isNull():
            available_width = max(1, int(self.width() * 0.43))
            available_height = max(1, int(self.height() * 0.62))
            wordmark = self._wordmark.scaled(
                available_width,
                available_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = 24
            y = (self.height() - wordmark.height()) // 2
            painter.drawPixmap(x, y, wordmark)

    @staticmethod
    def _cover_source_rect(
        source_width: int,
        source_height: int,
        target_width: int,
        target_height: int,
    ) -> QRect:
        if min(source_width, source_height, target_width, target_height) <= 0:
            return QRect()
        source_ratio = source_width / source_height
        target_ratio = target_width / target_height
        if source_ratio > target_ratio:
            crop_width = round(source_height * target_ratio)
            return QRect((source_width - crop_width) // 2, 0, crop_width, source_height)
        crop_height = round(source_width / target_ratio)
        return QRect(0, (source_height - crop_height) // 2, source_width, crop_height)
