"""Tappa 2 screens: Now Playing, queue, search, settings (DESIGN.md §4.4-4.7,
ACCEPTANCE N/Q/R/S), fed by client.backend (slipmatd or demo data).
"""
import ztos
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen

from client import backend
from widgets import Row, Cover, CenterLabel, fmt_ms


class MediaButton(ztos.RoundButton):
    """A transport round button with our own glyphs: prev / play / pause / next."""

    def __init__(self, kind: str, on_tap=None):
        super().__init__("", on_tap=on_tap)
        self._kind = kind
        self.setFixedSize(56, 56)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cx, cy, r = self.width() / 2.0, self.height() / 2.0, 24.0
        if self._p_to > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(ztos.accent())
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor("white"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r - 1.1, r - 1.1)
        p.setBrush(QColor("white"))
        p.setPen(Qt.NoPen)
        s = 9.0
        if self._kind == "play":
            p.drawPolygon([QPointF(cx - 4, cy - s), QPointF(cx - 4, cy + s), QPointF(cx + s, cy)])
        elif self._kind == "pause":
            p.drawRect(QRectF(cx - 7, cy - s, 5.5, 2 * s))
            p.drawRect(QRectF(cx + 1.5, cy - s, 5.5, 2 * s))
        elif self._kind == "prev":
            p.drawRect(QRectF(cx - s - 2, cy - s, 3, 2 * s))
            p.drawPolygon([QPointF(cx + s, cy - s), QPointF(cx + s, cy + s), QPointF(cx - 4, cy)])
        elif self._kind == "next":
            p.drawRect(QRectF(cx + s - 1, cy - s, 3, 2 * s))
            p.drawPolygon([QPointF(cx - s, cy - s), QPointF(cx - s, cy + s), QPointF(cx + 4, cy)])


class NowPlaying(ztos.Page):
    """Now Playing (N1-N3): big gradient cover, title/artist/album, seek bar,
    one transport group in the app bar."""

    def __init__(self, app):
        super().__init__("", header=False)
        self._app = app
        self.list.setContentsMargins(24, 0, 24, 24)
        track = backend.now_playing()
        self.space(48)
        self.add(Cover(230, track.get("album") or track.get("title", "")))
        self._title = CenterLabel(track.get("title", ""), 26, height=40)
        self._artist = CenterLabel(track.get("artist", ""), 16, QColor(255, 255, 255, 160), height=26)
        self._album = CenterLabel(track.get("album", ""), 14, QColor(255, 255, 255, 120),
                                  ztos.FONT_REGULAR, height=22)
        for w in (self._title, self._artist, self._album):
            self.add(w)
        self.space(10)
        self._seek = self.seekbar(track.get("position_ms", 0) / 1000.0,
                                  track.get("duration_ms", 0) / 1000.0,
                                  on_seek=lambda pos: backend.seek(pos * 1000.0))
        self.bar(MediaButton("prev", lambda: backend.transport("previous")),
                 MediaButton("play", lambda: backend.transport("playPause")),
                 MediaButton("next", lambda: backend.transport("next")))

    def shown(self):
        track = backend.now_playing()
        self._title.set_text(track.get("title", ""))
        self._artist.set_text(track.get("artist", ""))
        self._album.set_text(track.get("album", ""))
        self._seek.set_duration(track.get("duration_ms", 0) / 1000.0)
        self._seek.set_position(track.get("position_ms", 0) / 1000.0)


class QueuePage(ztos.Page):
    """The queue (Q1/Q2): rows as L1, the current one in accent; tap = jumpTo,
    hold = remove, 'clear' in the app bar."""

    def __init__(self):
        super().__init__("queue")
        self.list.setContentsMargins(17, 0, 16, 24)
        self.bar(ztos.RoundButton("delete", "clear", self._clear))

    def shown(self):
        self.clear()
        items, position = backend.queue_items()
        for i, it in enumerate(items):
            self.add(Row(it.get("title", ""), it.get("subtitle", ""), it.get("duration_ms", 0),
                         accent=(i == position),
                         on_tap=lambda i=i: backend.jump_to(i),
                         on_hold=lambda i=i: ztos.menu(self, [
                             ("remove from queue", lambda i=i: backend.remove_from_queue(i))])))

    def _clear(self):
        backend.clear_queue()
        self.shown()


class SearchPage(ztos.Page):
    """Search (R1/R2): field on top, results as list rows; 350 ms debounce."""

    def __init__(self):
        super().__init__("search")
        self.list.setContentsMargins(17, 0, 16, 24)
        self._debounce = QTimer(self, singleShot=True, interval=350)
        self._debounce.timeout.connect(self._run)
        self._box = self.textbox("search", placeholder="artist, album, song…",
                                 on_change=lambda _t: self._debounce.start())
        self._results = None

    def shown(self):
        self._box.field.setFocus(Qt.MouseFocusReason)

    def _run(self):
        q = self._box.text().strip()
        self._results = backend.search(q) if q else []
        # the field is item 0, the stretch is last: remove only the old results
        while self.list.count() > 2:
            item = self.list.takeAt(1)
            if item.widget() is not None:
                item.widget().deleteLater()
        for r in self._results:
            title = r.get("title") or r.get("name", "")
            self.list.insertWidget(self.list.count() - 1,
                                   Row(title, r.get("subtitle", ""), r.get("durationMs", 0)))


class SettingsPage(ztos.Page):
    """Minimal settings (S1/S2): sign in/out, refresh, quit, about (accent)."""

    def __init__(self):
        super().__init__("settings")
        self.entry("sign in", "slipmatd" if backend.live else "demo data (no slipmatd)",
                   lambda: backend.sign_in())
        self.entry("sign out", "", lambda: backend.sign_out())
        self.entry("refresh library", "", lambda: backend.refresh())
        self.entry("quit", "stop slipmatd", lambda: backend.quit_daemon())
        self.space(8)
        self.entry("about", f"{ztos.manifest().get('name', 'Zune HD')} "
                            f"v{ztos.manifest().get('version', '?')}", self._about)

    def _about(self):
        accent = ztos.accent()
        backend_name = "slipmatd" if backend.live else "demo data"
        ztos.message("about", f"{ztos.manifest().get('name')} v{ztos.manifest().get('version')}\n"
                              f"accent {accent.name()} from ztSettings\nbackend: {backend_name}",
                     ["ok"], lambda _c: None)
