"""Zune HD (ztOS SDK app, dev.oneplus2.zunehd) — home hub + now playing.

Built with the official ztOS SDK (Python + Qt Widgets, `ztos` module): pages
swing in with the shell's turnstile, rows tilt on press, the accent comes from
ztSettings. No QML/Qt Quick. Demo data from library.py; the slipmatd client
(slipmat/ipc.py) is wired in client.py.

Home = the Zune HD hub (DESIGN.md §4.1, measured on the reference and converted
to the SDK's 360x640 points, x1.204/x1.212): eight big lowercase entries
(278x55 canvas -> 334x67, x+15 -> 18, first row y+35 -> 42, step 55 -> 67,
font 45px -> 54px light, ls -1.8 -> -2.2), the quickplay round button top right
(33x33 -> 40x40 at x+245 -> 294, y+20 -> 24), and the now-playing strip pinned
at the bottom (299x40 -> 360x48) with the back arrow and the current track.
"""
import os

import ztos
import perf
import hub
import screens
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from library import NOW_PLAYING

# Hub menu of the Zune HD home (DESIGN.md §4.1). Only music / settings do
# something real for now; the rest push a placeholder (tappa 2 fills them).
HUB_ITEMS = ["music", "videos", "pictures", "radio",
             "marketplace", "internet", "apps", "settings"]

# DESIGN.md §4.1 converted to 360x640 points (canvas 299x528, x1.204 / x1.212)
HUB_ROW_H = 67          # 55 canvas
HUB_ROW_TOP = 42        # 24 (page) + 11 canvas
HUB_FONT_PX = 54        # 45 canvas
HUB_LS_PX = -2.2        # -1.8 canvas
HUB_X = 18              # 15 canvas
QUICK_SIZE = 40         # 33 canvas
QUICK_X, QUICK_Y = 294, 24   # 245 / 20 canvas
STRIP_H = 48            # 40 canvas
STRIP_FONT_PX = 14      # ~11.5 canvas


class HubEntry(ztos.Entry):
    """A big lowercase hub entry: same press/tilt/hold behaviour as ztos.Entry
    (_Pressable), only the drawing follows DESIGN.md §4.1's proportions."""

    def __init__(self, title: str, on_tap=None, on_hold=None):
        super().__init__(title, "", on_tap, on_hold)
        self.setFixedHeight(HUB_ROW_H)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(QColor("white"))                      # all entries white, crisp
        font = ztos._font(ztos.FONT_LIGHT, HUB_FONT_PX)
        font.setLetterSpacing(QFont.AbsoluteSpacing, HUB_LS_PX)
        p.setFont(font)
        fm = QFontMetricsF(p.font())
        text = self._title.lower()
        y = (self.height() + fm.ascent() - fm.descent()) / 2.0   # vertically centred
        p.drawText(QPointF(0, y), fm.elidedText(text, Qt.ElideRight, self.width()))


class QuickPlay(ztos.RoundButton):
    """The round quickplay button top right of the menu (DESIGN.md §4.1 H4):
    a ring with an up arrow; tapping it opens now playing."""

    def __init__(self, on_tap=None):
        super().__init__("", on_tap=on_tap)
        self.setFixedSize(QUICK_SIZE, QUICK_SIZE)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cx, cy, r = self.width() / 2.0, self.height() / 2.0, 17.0
        if self._p_to > 0:                            # pressed: accent fill, as the SDK's
            p.setPen(Qt.NoPen)
            p.setBrush(ztos.accent())
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor("white"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r - 1.0, r - 1.0)
        # up arrow
        p.drawLine(QPointF(cx, cy + 6.5), QPointF(cx, cy - 6.5))
        p.drawLine(QPointF(cx - 5.5, cy - 1.5), QPointF(cx, cy - 7.0))
        p.drawLine(QPointF(cx + 5.5, cy - 1.5), QPointF(cx, cy - 7.0))


class NowPlayingStrip(ztos.AppBar):
    """The pinned bottom strip (DESIGN.md §4.1): back arrow + current track
    (title — artist); tapping it opens now playing."""

    def __init__(self, track: dict, on_tap=None):
        super().__init__([])
        self.setFixedHeight(STRIP_H)
        self.setStyleSheet("background: #000000;")
        self._track = track
        self._on_tap = on_tap

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cy = self.height() / 2.0
        # back arrow, 13px, at x+17 (14 canvas)
        p.save()
        p.translate(17 + 6.5, cy)
        p.setPen(QPen(QColor(255, 255, 255, 180), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        ztos._glyph(p, "back", 13)
        p.restore()
        # title — artist, at x+38 (30 canvas)
        p.setPen(QColor(255, 255, 255, 200))
        p.setFont(ztos._font(ztos.FONT_SEMILIGHT, STRIP_FONT_PX))
        fm = QFontMetricsF(p.font())
        text = f"{self._track['title']} — {self._track['artist']}"
        p.drawText(QPointF(38, (self.height() + fm.ascent() - fm.descent()) / 2.0),
                   fm.elidedText(text, Qt.ElideRight, self.width() - 38 - 12))

    def mouseReleaseEvent(self, event):
        if self._on_tap:
            ztos.haptic("tap")
            self._on_tap()


class Home(ztos.Page):
    """The Zune HD home hub."""

    def __init__(self, app):
        super().__init__("", header=False)   # the hub has no page title/header
        self._app = app
        self.list.setContentsMargins(HUB_X, 0, 16, 24)
        self.space(HUB_ROW_TOP)
        for name in HUB_ITEMS:
            self.add(HubEntry(name, on_tap=lambda n=name: self._open(n),
                              on_hold=lambda n=name: self._hold(n)))
        strip = NowPlayingStrip(NOW_PLAYING, on_tap=self._open_now_playing)
        self.app_bar = strip                 # same as page.bar(), custom strip
        self.layout().addWidget(strip)
        self.quick = QuickPlay(on_tap=self._open_now_playing)
        self.quick.setParent(self)
        self.quick.setGeometry(QUICK_X, QUICK_Y, QUICK_SIZE, QUICK_SIZE)
        self.quick.raise_()

    def _open(self, name):
        ztos.haptic("tap")
        if name == "music":
            self._app.push(hub.MusicHub(self._app))
        elif name == "settings":
            self._app.push(screens.SettingsPage())
        else:
            page = ztos.Page(name)
            page.text(f"{name} — not in this client (music / settings only)")
            self._app.push(page)

    def _hold(self, name):
        ztos.menu(self, [(f"hold: {name}", None)])

    def _open_now_playing(self):
        self._app.push(screens.NowPlaying(self._app))


app = ztos.App()
perf.install(app)
home = Home(app)

# dev-only: ZUNE_NAV="music,songs" pushes pages after the entrance so
# `ztos-sdk run --shot` can photograph inner screens (ZTOS_SHOT_AFTER=5000)
_nav = [s for s in os.environ.get("ZUNE_NAV", "").split(",") if s]
if _nav:
    from PySide6.QtCore import QTimer

    def _go():
        for step in _nav:
            if step == "music":
                app._nav_hub = hub.MusicHub(app)
                app.push(app._nav_hub)
            elif step in ("artists", "albums", "songs", "playlists"):
                app._nav_hub.turn(["artists", "albums", "songs", "playlists"].index(step))
            elif step == "now":
                app.push(screens.NowPlaying(app))
            elif step == "queue":
                app.push(screens.QueuePage())
            elif step == "search":
                app.push(screens.SearchPage())
            elif step == "settings":
                app.push(screens.SettingsPage())

        if os.environ.get("ZUNE_SCROLL"):
            def _scroll():
                page = app.page
                inner = page.current() if isinstance(page, ztos.Pivot) else page
                if hasattr(inner, "_fling"):
                    inner._fling(2.5)
                    QTimer.singleShot(1500, _scroll)   # fling again, back and forth
            QTimer.singleShot(2500, _scroll)
    QTimer.singleShot(1500, _go)

app.run(home)
