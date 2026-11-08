"""Shared drawing pieces for the pages: list rows and gradient covers.

List rows follow the demo's songs list (ACCEPTANCE L1/L2): 299x59 canvas ->
360x71 logical, title 20px canvas -> 24px light at x+14 -> 17, subtitle 13px
canvas -> 15px grey rgba(255,255,255,0.5), duration at the right. Covers are
plain gradients, never placeholder text (A2/N1).
"""
import ztos
import art as art_mod
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

ROW_H = 71          # 59 canvas
TITLE_PX = 24       # 20 canvas
SUB_PX = 15         # 13 canvas
LIST_X = 17         # 14 canvas
THUMB = 48          # square artwork thumb on song rows


def cover_colors(text: str):
    """Deterministic gradient pair from the title (no text on covers).
    QColor.fromHsl is on a 0-255 scale, so lightness 150-170 is a bright cover."""
    h = 0
    for ch in text:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    hue = h % 360
    hue2 = (hue + 40 + (h >> 8) % 80) % 360
    return QColor.fromHsl(hue, 165, 168), QColor.fromHsl(hue2, 185, 105)


def draw_cover(p: QPainter, rect: QRectF, title: str):
    c1, c2 = cover_colors(title)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    p.fillRect(rect, g)


def fmt_ms(ms) -> str:
    s = int(max(0, ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"


class Thumb(QWidget):
    """48px artwork thumb as its OWN child widget: when the image arrives it
    redraws only itself (144px square at DPR 3) and NEVER invalidates the row's
    text cache — that was the 98%-CPU scroll bug (each thumb arrival used to
    force a full-DPR text re-render of the row)."""

    def __init__(self, template: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(THUMB, THUMB)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._t = template
        self._img = None
        if template:
            art_mod.add_listener(self._on_art, template)

    def _on_art(self, template, path, ok):
        if ok and template == self._t:
            dpr = self.devicePixelRatioF() or 1.0
            self._img = art_mod.thumb_image(path, int(THUMB * dpr))   # shared, pre-scaled once
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        if self._img is not None:
            p.drawImage(self.rect(), self._img)
        else:
            p.fillRect(self.rect(), QColor(38, 38, 38))   # neutral placeholder, no letters


class Row(ztos.Entry):
    """A list row: optional 48px artwork thumb (child widget, async from the
    disk cache, neutral grey placeholder — never letters), title, grey
    subtitle, duration at the right (L1/L2). Fonts and elided strings are
    cached: draw() only recomposes text when the data changes."""

    def __init__(self, title: str, subtitle: str = "", duration_ms: int = 0,
                 on_tap=None, on_hold=None, accent: bool = False, art: str = ""):
        super().__init__(title, "", on_tap, on_hold)
        self.setFixedHeight(ROW_H)
        self._subtitle = subtitle
        self._duration = duration_ms
        self._accent = accent
        self._art = art or ""
        self._tx = THUMB + 12 if self._art else 0
        self._f_title = ztos._font(ztos.FONT_LIGHT, TITLE_PX)
        self._f_sub = ztos._font(ztos.FONT_REGULAR, SUB_PX)
        self._elide = {}
        if self._art:
            t = Thumb(self._art, self)
            t.move(0, (ROW_H - THUMB) // 2)
            t.show()

    def _elided(self, fm, text, width):
        key = (text, round(width))
        out = self._elide.get(key)
        if out is None:
            out = fm.elidedText(text, Qt.ElideRight, width)
            self._elide[key] = out
        return out

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(ztos.accent() if self._accent else QColor("white"))
        p.setFont(self._f_title)
        fm = QFontMetricsF(p.font())
        p.drawText(QPointF(self._tx, 30), self._elided(fm, self._title, self.width() - self._tx - 70))
        p.setPen(QColor(255, 255, 255, 127))
        p.setFont(self._f_sub)
        fm2 = QFontMetricsF(p.font())
        p.drawText(QPointF(self._tx, 58), self._elided(fm2, self._subtitle, self.width() - self._tx - 90))
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
