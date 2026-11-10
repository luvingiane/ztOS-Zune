"""Shared drawing pieces for the pages: list rows and gradient covers.

List rows follow the demo's songs list (ACCEPTANCE L1/L2): 299x59 canvas ->
360x71 logical, title 20px canvas -> 24px light at x+14 -> 17, subtitle 13px
canvas -> 15px grey rgba(255,255,255,0.5), duration at the right. Covers are
plain gradients, never placeholder text (A2/N1).
"""
import ztos
import art as art_mod
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPen
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
    if art_mod.noimg():                     # covers off: flat grey, no gradient
        p.fillRect(rect, QColor(38, 38, 38))
        return
    c1, c2 = cover_colors(title)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    p.fillRect(rect, g)


def fmt_ms(ms) -> str:
    s = int(max(0, ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"


class CircleButton(ztos.RoundButton):
    """The SDK's RoundButton without the press "lean" on the GPU layer.

    The lean (`_Pressable._lean_begin`) covers the WHOLE widget rectangle with
    an opaque black quad (sdk __init__.py:_lean_quads) to hide the flat
    button under the tilted copy, so on the app bar a square overlay appears
    on press. Skipping the lean keeps the supported press feedback (the ring
    fills with the accent, `_press_set`) and never touches the GL layer."""

    def _lean_begin(self):
        self._gl_lean = False

    def set_label(self, label: str):
        changed = self._label != label
        super().set_label(label)
        if changed:
            self.redraw()                 # same stale-cache reason as set_glyph

    def set_glyph(self, glyph: str):
        # The SDK widget draws itself once into a cached picture and only
        # copies it on repaint; RoundButton.set_glyph just calls update(), so
        # the OLD glyph stayed on screen after a play/pause change (the button
        # looked inverted, always one state behind). redraw() drops the cache.
        changed = self._glyph != glyph
        super().set_glyph(glyph)
        if changed:
            self.redraw()


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
                 on_tap=None, on_hold=None, accent: bool = False, art: str = "",
                 available: bool = True):
        super().__init__(title, "", on_tap, on_hold)
        self.setFixedHeight(ROW_H)
        self._subtitle = subtitle
        self._duration = duration_ms
        self._accent = accent
        self._available = available
        self._right = 0              # extra right padding (queue grip)
        self._lift = False           # row being dragged: lighter background
        self._art = "" if (art and art_mod.blocked(art)) else (art or "")   # covers off: no thumb box at all
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
        if self._lift:
            p.fillRect(QRectF(-LIST_X, 0, self.width() + 2 * LIST_X, self.height()), QColor(255, 255, 255, 34))
        if not self._available:
            p.setOpacity(0.38)            # unavailable: whole row dimmed
        p.setPen(ztos.accent() if self._accent else QColor("white"))
        p.setFont(self._f_title)
        fm = QFontMetricsF(p.font())
        p.drawText(QPointF(self._tx, 30), self._elided(fm, self._title, self.width() - self._tx - 70 - self._right))
        p.setPen(QColor(255, 255, 255, 127))
        p.setFont(self._f_sub)
        fm2 = QFontMetricsF(p.font())
        p.drawText(QPointF(self._tx, 58), self._elided(fm2, self._subtitle, self.width() - self._tx - 90 - self._right))
        if not self._available:
            # "not available" mark (circle with a slash) where the duration goes
            p.setOpacity(0.7)
            p.setPen(QPen(QColor("white"), 1.6))
            cx, cy, r = self.width() - 11.0 - self._right, 50.0, 8.0
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.drawLine(QPointF(cx - r * 0.7, cy + r * 0.7), QPointF(cx + r * 0.7, cy - r * 0.7))
        elif self._duration:
            text = fmt_ms(self._duration)
            p.drawText(QPointF(self.width() - self._right - fm2.horizontalAdvance(text) - 2, 58), text)

    def set_available(self, v: bool):
        if v != self._available:
            self._available = v
            self.redraw()


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


def warm_cache(widget) -> bool:
    """Build an SDK `_Pressable`'s cached picture NOW (same code as its first
    paintEvent) so the paint during a fling is a plain copy. On the phone the
    first paint of a text row costs 25-30 ms at DPR 3 (sdk __init__.py:1070);
    two new rows per frame in a fling saturated a core (the B log shows
    pressable_paint 130-250 ms per second while scrolling)."""
    from PySide6.QtGui import QPixmap
    if widget.width() < 2 or widget.height() < 2:
        return False
    if widget.height() > 2 * ROW_H:
        return False        # tall single widgets (album grid): a full-DPR pixmap would be tens of Mpx
    ratio = widget.devicePixelRatioF()
    size = widget.size() * ratio
    cache = getattr(widget, "_cache", None)
    if cache is not None and cache.size() == size:
        return False
    pic = QPixmap(size)
    pic.setDevicePixelRatio(ratio)
    pic.fill(Qt.transparent)
    q = QPainter(pic)
    q.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    widget.draw(q)
    q.end()
    widget._cache = pic
    return True


class RowWarmer:
    """Idle-time cache warming for the rows of a page: one row per tick, only
    when nobody is touching or flinging the page, nearest rows to the viewport
    first. Stops itself when everything within reach is warm."""

    def __init__(self, page, interval=45):
        from PySide6.QtCore import QTimer
        self.page = page
        self.timer = QTimer(page, interval=interval)
        self.timer.timeout.connect(self._tick)

    def start(self):
        self.timer.start()

    def _tick(self):
        page = self.page
        if not page.isVisible():
            return
        try:
            if page._flinging() or ztos.App.current._finger.active:
                return
        except Exception:
            pass
        top = page._scroll if hasattr(page, "_scroll") else 0.0
        view = max(page.viewport.height(), 400)
        lo, hi = top - view, top + 3 * view
        best, best_d = None, None
        for i in range(page.list.count()):
            wdg = page.list.itemAt(i).widget()
            if not isinstance(wdg, ztos.Entry) or wdg.height() < 2 or wdg.height() > 2 * ROW_H:
                continue
            y = wdg.y()
            if y < lo or y > hi:
                continue
            cache = getattr(wdg, "_cache", None)
            if cache is not None and cache.size() == wdg.size() * wdg.devicePixelRatioF():
                continue
            d = abs(y - top)
            if best is None or d < best_d:
                best, best_d = wdg, d
        if best is None:
            self.timer.stop()
            return
        warm_cache(best)
