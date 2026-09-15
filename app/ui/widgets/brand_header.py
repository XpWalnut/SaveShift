from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.core.resources import get_resource_path
from app.ui import theme


class BrandHeader(QWidget):
    """Compact, restrained header derived from the refined Save Shift logo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BrandHeader")
        self.setFixedHeight(92)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._logo = QPixmap(
            str(get_resource_path("assets/ui/SaveShift-RefinedLogo.png"))
        )

    @property
    def assets_available(self) -> bool:
        return not self._logo.isNull()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor("#171522"))
        gradient.setColorAt(0.55, QColor(theme.WINDOW_BACKGROUND))
        gradient.setColorAt(1, QColor("#121220"))
        painter.fillRect(self.rect(), gradient)
        painter.setPen(QColor(theme.CARD_BORDER))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        if not self._logo.isNull():
            source = self._wordmark_source_rect(
                self._logo.width(),
                self._logo.height(),
            )
            target_width = min(330, max(230, self.width() // 3))
            painter.drawPixmap(
                QRect(24, 14, target_width, 45),
                self._logo,
                source,
            )

        painter.setPen(QColor(theme.TEXT_SECONDARY))
        painter.setFont(QFont("Segoe UI Variable", 10))
        painter.drawText(25, 76, "Co-op, continued.")

    @staticmethod
    def _wordmark_source_rect(width: int, height: int) -> QRect:
        return QRect(
            round(width * 0.11),
            round(height * 0.735),
            round(width * 0.79),
            round(height * 0.115),
        )
