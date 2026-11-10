"""Now Playing, built the ztmetro way (same parts as the official `music` app,
ztOS/apps/music/player_view.py): a standard `ztos.Page` with its header, the
cover, title (24) / artist (14, grey), the SDK's own `ztos.SeekBar`, and the
five transport buttons in the page's app bar (queue, prev, play/pause, next,
options) - no absolute layout, no safe-area arithmetic (the shell sizes the
window between its status and nav bars).

Extras kept from the earlier player:
- blurred cover as page background, OPTIONAL (Settings -> "player blur",
  store key `blur_bg`, default on). Computed once per track on a worker thread
  (never on the GUI thread): a cheap double downscale + one smooth upscale.
- monotonic position model: slipmatd publishes a snapshot every 500 ms
  (serve.rs:39), the bar interpolates in between and never goes backward on a
  late snapshot; a position-only snapshot touches nothing but the bar.
- the options are the SDK's standard menu (`ztos.menu`).
"""
import time

import ztos
import icons
from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter
from PySide6.QtWidgets import QLabel, QWidget

from art import Artwork, local_art, image_for
from client import backend, rtitle
from widgets import CircleButton, cover_colors

COVER_MAX = 260


def blur_enabled() -> bool:
    return bool(ztos.store("zunehd").get("blur_bg", True))


def make_blur_bg(img, w: int, h: int):
    """Blurred background in a few ms: downscale the cover twice (32 px then
    12 px, smooth = area averaging) and upscale once, smooth, to the window.
    Pure Qt image ops, no Python pixel loops; safe on a worker thread."""
    if img is None or img.isNull():
        return None
    small = img.scaled(32, 32, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    small = small.scaled(12, 12, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(max(1, w), max(1, h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


class _BlurWorker(QThread):
    done = Signal(str, object)

    def __init__(self, key, img, w, h, parent=None):
        super().__init__(parent)
        self._key, self._img, self._w, self._h = key, img.copy(), w, h

    def run(self):
        self.done.emit(self._key, make_blur_bg(self._img, self._w, self._h))


class PositionModel:
    """Anchor = (position, monotonic time of the snapshot). While playing the
    position interpolates; a snapshot lower than the interpolated position
    (late / out of order) is ignored unless the track changed, playback
    paused or the user sought."""

    def __init__(self):
        self.pos = 0.0
        self.t = 0.0
        self.dur = 0.0
        self.playing = False
        self.key = ""

    def anchor(self, pos_ms, dur_ms, playing, key=""):
        now_pos = self.current()
        new = pos_ms / 1000.0
        changed = key != self.key
        self.key = key
        self.dur = dur_ms / 1000.0
        was_playing = self.playing
        self.playing = bool(playing)
        if new < now_pos - 0.150 and not changed and playing and was_playing:
            return False                         # stale snapshot: ignore
        self.pos, self.t = new, time.monotonic()
        return True

    def seek_to(self, seconds):
        self.pos, self.t = seconds, time.monotonic()

    def current(self):
        if self.playing:
            return min(self.dur if self.dur > 0 else self.pos, self.pos + (time.monotonic() - self.t))
        return self.pos


class _Backdrop(QWidget):
    """Child of the page's viewport, under the body: paints the page-wide
    background (blurred cover / gradient) offset so it lines up with the page."""

    def __init__(self, page, viewport):
        super().__init__(viewport)
        self._page = page
        self.setGeometry(0, 0, 4000, 4000)        # clipped by the viewport
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lower()

    def paintEvent(self, event):
        p = QPainter(self)
        p.translate(0, -self._page.viewport.y())
        self._page.paint_backdrop(p)


class NowPlaying(ztos.Page):
    """The Now Playing page. Back pops it. It never scrolls."""

    def __init__(self, app):
        super().__init__("now playing", scroll=False)
        self._app = app
        self.view = self                       # compat: old code reached page.view
        self._track = {}
        self._track_key = ""
        self._model = PositionModel()
        self._bg = None                        # blurred background (window size)
        self._bg_key = None
        self._worker = None
        self._blur_applied = blur_enabled()
        # the page background is ours to paint (blur): viewport/body transparent
        # (the SDK viewport paints opaque black: our backdrop is a child under the body)
        self.body.setStyleSheet("background: transparent;")
        self._backdrop = _Backdrop(self, self.viewport)
        self.list.setContentsMargins(ztos.MARGIN, 8, ztos.MARGIN, 8)

        self._cover = Artwork(COVER_MAX, "", "", art_size=512)
        self.list.insertWidget(self.list.count() - 1, self._cover, 0, Qt.AlignHCenter)
        self.space(14)
        self._title = self._label(24, ztos.FONT_LIGHT, "white")
        self._artist = self._label(14, ztos.FONT_REGULAR, "rgba(255,255,255,150)")
        self.space(10)
        self._seek = self.add(ztos.SeekBar(0.0, 0.0, on_seek=self._on_seek))

        self.ctrl = {}
        for kind, cb in (("queue", lambda: app.push(_queue_page())),
                         ("prev", lambda: backend.transport("previous")),
                         ("play", lambda: backend.transport("playPause")),
                         ("next", lambda: backend.transport("next")),
                         ("more", self._open_options)):
            self.ctrl[kind] = CircleButton(icons.path(kind), on_tap=cb)
        bar = self.bar(*self.ctrl.values())
        # the SDK bar has 16 px margins: 5 buttons of 68 px (340) do not fit 360.
        # Configuring OUR instance's layout (the SDK is untouched).
        bar.layout().setContentsMargins(8, 2, 8, 4)
        bar.layout().setSpacing(0)

        self._clock = QTimer(self, interval=500)
        self._clock.timeout.connect(self._tick)
        self._clock.start()
        backend.snapshot_changed.connect(self._refresh)

    # ---- building blocks -----------------------------------------------------
    def _label(self, size, family, color):
        lab = QLabel("")
        lab.setFont(ztos._font(family, size))
        lab.setStyleSheet(f"color: {color}; background: transparent;")
        lab.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        lab.setFixedHeight(int(size * 1.7))
        self.add(lab)
        return lab

    @staticmethod
    def _set_elided(label, text):
        fm = QFontMetricsF(label.font())
        w = max(60, (label.width() if label.width() > 60 else 328) - 4)
        label.setText(fm.elidedText(text, Qt.ElideRight, w))

    def _on_seek(self, seconds):
        self._model.seek_to(seconds)
        backend.seek(seconds * 1000.0)

    # ---- page lifecycle -------------------------------------------------------
    def _drag_to(self, raw):
        pass                        # no vertical drag on the player

    def _fling(self, v):
        pass

    def shown(self):
        if blur_enabled() != self._blur_applied:        # toggled in Settings meanwhile
            self.apply_blur_setting()
        self._refresh()

    def _refresh(self):
        if not self.isVisible():
            return                      # snapshots arrive every 500 ms: skip when hidden
        t = backend.now_playing()
        t["favorite"] = self._favorite_flag(t)
        self.set_track(t)

    def set_track(self, t: dict):
        """Snapshot in. A position-only snapshot touches only the seek model
        and the play glyph; a real track change updates texts, cover, blur."""
        key = f"{t.get('title', '')}|{t.get('artist', '')}|{t.get('track_id', '')}|{t.get('art_path', '')}"
        changed = key != self._track_key
        self._track = t
        self._track_key = key
        playing = bool(t.get("playing"))
        glyph = icons.path("pause" if playing else "play")
        play = self.ctrl["play"]
        if play._glyph != glyph:
            play.set_glyph(glyph)
        if changed:
            self._set_elided(self._title, t.get("title", ""))
            sub = f"{t.get('artist', '')} - {t.get('album', '')}".strip(" -")
            self._set_elided(self._artist, sub)
            self._cover.set_template(t.get("artwork_template", ""), t.get("album") or t.get("title", ""))
            art = t.get("art_path", "")
            p = local_art(art, 512) if art else None
            if p and image_for(p) is not None:
                self._cover._img = image_for(p)
                self._cover.redraw()
            self._request_blur(key)
        self._model.anchor(t.get("position_ms", 0), t.get("duration_ms", 0), playing, key)
        self._seek.set_duration(self._model.dur)
        self._seek.set_position(self._model.current())

    def _tick(self):
        # interpolate the bar between the 500 ms snapshots (repaints only it)
        if self._model.playing and self._seek.isVisible():
            self._seek.set_position(self._model.current())

    # ---- blurred background (optional) ----------------------------------------
    def _request_blur(self, key):
        img = self._cover._img
        if not blur_enabled() or img is None or img.isNull():
            if self._bg is not None:
                self._bg = None
                self.update()
            return
        self._bg_key = key
        w = self.window().width() if self.window().width() > 1 else self.width()
        h = self.window().height() if self.window().height() > 1 else self.height()
        self._worker = _BlurWorker(key, img, int(w), int(h), self)
        self._worker.done.connect(self._blur_ready)
        self._worker.start()

    def _blur_ready(self, key, image):
        if key == self._track_key and blur_enabled():
            self._bg = image
            self.update()
            self._backdrop.update()

    def apply_blur_setting(self):
        """Settings toggled: take effect at once (no restart)."""
        self._bg = None
        self._blur_applied = blur_enabled()
        self._request_blur(self._track_key)
        self.update()
        self._backdrop.update()

    def paintEvent(self, event):
        p = QPainter(self)
        self.paint_backdrop(p)

    def paint_backdrop(self, p):
        w, h = float(self.width()), float(self.height())
        p.fillRect(QRectF(0, 0, w, h), QColor("black"))
        if not blur_enabled():
            return
        if self._bg is not None:
            p.drawImage(QRectF(0, 0, w, h), self._bg)
            p.fillRect(QRectF(0, 0, w, h), QColor(0, 0, 0, 170))     # veil: keep text legible
        else:
            c1, _c2 = cover_colors(self._track.get("album") or self._track.get("title") or "")
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0.0, QColor(c1).darker(320))
            g.setColorAt(1.0, QColor(0, 0, 0))
            p.fillRect(QRectF(0, 0, w, h), g)

    # ---- options (the SDK's standard menu) --------------------------------------
    def _open_options(self):
        t = backend.now_playing()
        fav = bool(self._track.get("favorite"))
        sid = self._song_id()
        items = [
            ("remove from favorites" if fav else "add to favorites",
             lambda: backend.write("unfavorite" if fav else "favorite", sid)),
            (f"go to album: {t.get('album', '')}", lambda: self._go("albums", t.get("album", ""), "album")),
            (f"go to artist: {t.get('artist', '')}", lambda: self._go("artists", t.get("artist", ""), "artist")),
            (f"shuffle: {'on' if t.get('shuffle') else 'off'}", lambda: backend.set_shuffle(not t.get("shuffle"))),
            (f"repeat: {t.get('repeat', 'none')}", lambda: backend.set_repeat(_next_repeat(t.get("repeat", "none")))),
        ]
        self._menu = ztos.menu(self.ctrl["more"], items)

    def _song_id(self):
        items, pos = backend.queue_items()
        if items and 0 <= pos < len(items):
            return items[pos].get("id") or ""
        return self._track.get("track_id") or ""

    def _go(self, view, name, kind):
        for row in backend.browse(view):
            if rtitle(row) == name:
                from hub import DetailPage
                ztos.App.current.push(DetailPage(row.get("pageKind", kind), row.get("id", ""), rtitle(row)))
                return

    def _favorite_flag(self, t):
        """Favorite state of the current track, from the cached songs rows."""
        with backend._lock:
            rows = backend._rows.get("songs")
        if rows:
            for r in rows:
                if r.get("title") == t.get("title") and r.get("artist") == t.get("artist"):
                    return bool(r.get("favorite"))
        return False


def _next_repeat(cur):
    order = ["none", "one", "all"]
    return order[(order.index(cur) + 1) % len(order)] if cur in order else "all"


def _queue_page():
    from screens import QueuePage
    return QueuePage()
