"""Shared drawing pieces for the pages: list rows and gradient covers.

List rows follow the demo's songs list (ACCEPTANCE L1/L2): 299x59 canvas ->
360x71 logical, title 20px canvas -> 24px light at x+14 -> 17, subtitle 13px
canvas -> 15px grey rgba(255,255,255,0.5), duration at the right. Covers are
plain gradients, never placeholder text (A2/N1).
"""
import ztos
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter

ROW_H = 71          # 59 canvas
TITLE_PX = 24       # 20 canvas
SUB_PX = 15         # 13 canvas
LIST_X = 17         # 14 canvas


def cover_colors(text: str):
    """Deterministic gradient pair from the title (no text on covers)."""
    h = 0
    for ch in text:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    hue = h % 360
    hue2 = (hue + 40 + (h >> 8) % 80) % 360
    return QColor.fromHsl(hue, 150, 72), QColor.fromHsl(hue2, 165, 42)


def draw_cover(p: QPainter, rect: QRectF, title: str):
    c1, c2 = cover_colors(title)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    p.fillRect(rect, g)


def fmt_ms(ms) -> str:
    s = int(max(0, ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"


class Row(ztos.Entry):
    """A list row: title, grey subtitle, duration at the right (L1/L2)."""

    def __init__(self, title: str, subtitle: str = "", duration_ms: int = 0,
                 on_tap=None, on_hold=None, accent: bool = False):
        super().__init__(title, "", on_tap, on_hold)
        self.setFixedHeight(ROW_H)
        self._subtitle = subtitle
        self._duration = duration_ms
        self._accent = accent

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(ztos.accent() if self._accent else QColor("white"))
        p.setFont(ztos._font(ztos.FONT_LIGHT, TITLE_PX))
        fm = QFontMetricsF(p.font())
        p.drawText(QPointF(0, 30), fm.elidedText(self._title, Qt.ElideRight, self.width() - 70))
        p.setPen(QColor(255, 255, 255, 127))
        p.setFont(ztos._font(ztos.FONT_REGULAR, SUB_PX))
        fm2 = QFontMetricsF(p.font())
        p.drawText(QPointF(0, 58), fm2.elidedText(self._subtitle, Qt.ElideRight, self.width() - 90))
        if self._duration:
            text = fmt_ms(self._duration)
            p.drawText(QPointF(self.width() - fm2.horizontalAdvance(text) - 2, 58), text)


class Cover(ztos.Entry):
    """A square gradient cover (N1: no placeholder text, ever)."""

    def __init__(self, size: int, title: str):
        super().__init__("", "")
        self._cover_title = title
        self.setFixedSize(size, size)

    def draw(self, p: QPainter):
        draw_cover(p, QRectF(0, 0, self.width(), self.height()), self._cover_title)


class CenterLabel(ztos.Entry):
    """A centred text line (used on Now Playing); `size`/`color` at construction."""

    def __init__(self, text: str, size: float, color=None, families=None, height: int = 34):
        super().__init__("", "")
        self._text, self._size = text, size
        self._color = color or QColor("white")
        self._families = families or ztos.FONT_LIGHT
        self.setFixedHeight(height)

    def set_text(self, text: str):
        self._text = text
        self.redraw()
        self.content_changed()

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(self._color)
        p.setFont(ztos._font(self._families, self._size))
        p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignCenter, self._text)
