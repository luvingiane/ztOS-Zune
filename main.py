"""Zune HD (ztOS SDK app, dev.oneplus2.zunehd) — TAPPA 1: the home hub only.

Built with the official ztOS SDK (Python + Qt Widgets, `ztos` module): pages
swing in with the shell's turnstile, rows tilt on press, the accent comes from
ztSettings. No QML/Qt Quick. Demo data only in this stage — the slipmatd
client (slipmat/ipc.py) is wired in tappa 2.

Home = the Zune HD hub: a vertical list of eight big lowercase entries
(music, videos, pictures, radio, marketplace, internet, apps, settings), a
now-playing strip pinned at the bottom, status bar drawn by the shell on
device. Geometry follows DESIGN.md (converted to the SDK's 360x640 points).
"""
import ztos
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter
from PySide6.QtWidgets import QLabel

# Hub menu of the Zune HD home (DESIGN.md §4.1). In this client only music /
# marketplace / settings do something; the rest push a placeholder (tappa 2).
HUB_ITEMS = ["music", "videos", "pictures", "radio",
             "marketplace", "internet", "apps", "settings"]

# DESIGN.md §4.1 measured on the reference: items 278x55 on a 299-canvas
# (45px light text) -> on the SDK's 360x640 points: ~64px rows, ~40px light.
HUB_ROW_H = 64
HUB_FONT_PX = 40
STRIP_H = 48          # bottom now-playing strip (299x40 canvas -> 48 points)


class HubEntry(ztos.Entry):
    """A big lowercase hub entry: same press/tilt/hold behaviour as ztos.Entry
    (_Pressable), only the drawing is bigger (DESIGN.md §4.1)."""

    def __init__(self, title: str, on_tap=None, on_hold=None):
        super().__init__(title, "", on_tap, on_hold)
        self.setFixedHeight(HUB_ROW_H)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(QColor("white"))                      # all entries white, crisp
        p.setFont(ztos._font(ztos.FONT_LIGHT, HUB_FONT_PX))  # runtime's font helper
        fm = QFontMetricsF(p.font())
        text = self._title.lower()
        y = (self.height() + fm.ascent() - fm.descent()) / 2.0   # vertically centred
        p.drawText(QPointF(0, y), fm.elidedText(text, Qt.ElideRight, self.width()))


class NowPlayingStrip(ztos.AppBar):
    """The pinned bottom strip (DESIGN.md §4.1): back glyph + current track.
    AppBar is the SDK's bottom bar; we pin it to 48px and put a label in it."""

    def __init__(self, text: str, on_tap=None):
        super().__init__([])
        self.setFixedHeight(STRIP_H)
        self.setStyleSheet("background: #000000;")
        self._on_tap = on_tap
        self._label = QLabel(text)
        self._label.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 13px;")
        self._row.insertWidget(0, self._label)   # before the trailing stretch

    def mouseReleaseEvent(self, event):
        if self._on_tap:
            ztos.haptic("tap")
            self._on_tap()


class Home(ztos.Page):
    """The Zune HD home hub."""

    def __init__(self, app):
        super().__init__("", header=False)   # the hub has no page title/header
        self._app = app
        self.space(10)
        for name in HUB_ITEMS:
            self.add(HubEntry(name, on_tap=lambda n=name: self._open(n),
                              on_hold=lambda n=name: self._hold(n)))
        strip = NowPlayingStrip("nothing playing yet", on_tap=self._open_now_playing)
        self.app_bar = strip                 # same as page.bar(), custom strip
        self.layout().addWidget(strip)

    def _open(self, name):
        ztos.haptic("tap")
        page = ztos.Page(name)
        page.text(f"{name} — tappa 2: collegamento a slipmatd")
        self._app.push(page)

    def _hold(self, name):
        ztos.menu(self, [(f"hold: {name}", None)])

    def _open_now_playing(self):
        page = ztos.Page("now playing")
        page.text("tappa 2: schermata In riproduzione")
        self._app.push(page)


app = ztos.App()
app.run(Home(app))
