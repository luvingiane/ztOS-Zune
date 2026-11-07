"""Screens: Now Playing, queue, search, settings (stage 3).

Now Playing (DESIGN §4.4, ACCEPTANCE N): cover (snapshot art_path, else
gradient), title/artist/album, seek bar with times, ONE transport group
(prev/play/next) + shuffle/repeat + queue in the app bar, volume slider.
Queue (Q): rows, current in accent, tap=jumpTo, hold=remove, clear in bar.
Search (R): field + filter (all/songs/albums/artists/playlists, remembered),
results as rows, 350 ms debounce. Settings (S): stage/mode, sign in/out,
refresh, quit daemon, about.
"""
import ztos
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen

from art import Artwork, local_art, image_for, prewarm
from client import backend, rtitle
from widgets import Row, CenterLabel, fmt_ms


class MediaButton(ztos.RoundButton):
    """Transport round button with our own glyphs: prev/play/pause/next/
    shuffle/repeat. `toggle` glyphs fill with the accent when on."""

    def __init__(self, kind: str, on_tap=None, size: int = 52, on: bool = False):
        super().__init__("", on_tap=on_tap)
        self._kind = kind
        self._on = on
        self.setFixedSize(size, size)

    def set_on(self, on: bool):
        self._on = on
        self.redraw()
        self.content_changed()

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = min(self.width(), self.height()) / 2.0 - 4.0
        pressed = self._p_to > 0
        if pressed or (self._kind in ("shuffle", "repeat") and self._on):
            p.setPen(Qt.NoPen)
            p.setBrush(ztos.accent())
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor("white"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r - 1.0, r - 1.0)
        p.setBrush(QColor("white"))
        p.setPen(Qt.NoPen)
        s = min(9.0, r * 0.5)
        k = self._kind
        if k == "play":
            p.drawPolygon([QPointF(cx - 4, cy - s), QPointF(cx - 4, cy + s), QPointF(cx + s, cy)])
        elif k == "pause":
            p.drawRect(QRectF(cx - 7, cy - s, 5.5, 2 * s))
            p.drawRect(QRectF(cx + 1.5, cy - s, 5.5, 2 * s))
        elif k == "prev":
            p.drawRect(QRectF(cx - s - 2, cy - s, 3, 2 * s))
            p.drawPolygon([QPointF(cx + s, cy - s), QPointF(cx + s, cy + s), QPointF(cx - 4, cy)])
        elif k == "next":
            p.drawRect(QRectF(cx + s - 1, cy - s, 3, 2 * s))
            p.drawPolygon([QPointF(cx - s, cy - s), QPointF(cx - s, cy + s), QPointF(cx + 4, cy)])
        elif k == "shuffle":
            p.setPen(QPen(QColor("white"), 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - s, cy - s * 0.4), QPointF(cx + s, cy - s * 0.4))
            p.drawLine(QPointF(cx - s, cy + s * 0.4), QPointF(cx + s, cy + s * 0.4))
            p.drawPolygon([QPointF(cx + s - 3, cy - s * 0.4 - 3), QPointF(cx + s + 1, cy - s * 0.4),
                           QPointF(cx + s - 3, cy - s * 0.4 + 3)])
            p.drawPolygon([QPointF(cx - s + 3, cy + s * 0.4 + 3), QPointF(cx - s - 1, cy + s * 0.4),
                           QPointF(cx - s + 3, cy + s * 0.4 - 3)])
        elif k == "repeat":
            p.setPen(QPen(QColor("white"), 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - s, cy - s, 2 * s, 2 * s), 30 * 16, 300 * 16)
            p.drawPolygon([QPointF(cx + s - 2, cy - s + 4), QPointF(cx + s + 3, cy - s + 1),
                           QPointF(cx + s - 1, cy - s - 3)])


class NowPlaying(ztos.Page):
    """Now Playing: cover, title/artist/album, seek, volume, transport."""

    def __init__(self, app):
        super().__init__("", header=False)
        self._app = app
        self.list.setContentsMargins(24, 0, 24, 24)
        self.space(40)
        self._cover = Artwork(230, "", "", art_size=512)
        self.add(self._cover)
        self._title = CenterLabel("", 26, height=40)
        self._artist = CenterLabel("", 16, QColor(255, 255, 255, 160), height=26)
        self._album = CenterLabel("", 14, QColor(255, 255, 255, 120), ztos.FONT_REGULAR, height=22)
        for w in (self._title, self._artist, self._album):
            self.add(w)
        self.space(8)
        self._seek = self.seekbar(0.0, 0.0, on_seek=lambda pos: backend.seek(pos * 1000.0))
        self._vol = self.slider("volume", 100, on_change=lambda v: backend.set_volume(v / 100.0))
        self._play = MediaButton("play", lambda: backend.transport("playPause"))
        self._shuffle = MediaButton("shuffle", lambda: backend.set_shuffle(not self._shuffle._on))
        self._repeat = MediaButton("repeat", self._cycle_repeat)
        self.bar(MediaButton("prev", lambda: backend.transport("previous"), 48),
                 self._play, MediaButton("next", lambda: backend.transport("next"), 48),
                 self._shuffle, self._repeat,
                 MediaButton("more", lambda: app.push(QueuePage()), 48))
        backend.snapshot_changed.connect(self._refresh)

    def _cycle_repeat(self):
        order = ["none", "one", "all"]
        cur = (backend.now_playing().get("repeat") or "none")
        backend.set_repeat(order[(order.index(cur) + 1) % len(order)] if cur in order else "all")

    def shown(self):
        self._refresh()

    def _refresh(self):
        t = backend.now_playing()
        self._title.set_text(t.get("title", ""))
        self._artist.set_text(t.get("artist", ""))
        self._album.set_text(t.get("album", ""))
        self._seek.set_duration(t.get("duration_ms", 0) / 1000.0)
        self._seek.set_position(t.get("position_ms", 0) / 1000.0)
        self._play._kind = "pause" if t.get("playing") else "play"
        self._play.redraw(); self._play.content_changed()
        self._shuffle.set_on(bool(t.get("shuffle")))
        self._repeat.set_on(t.get("repeat", "none") != "none")
        if t.get("volume") is not None:
            self._vol.set_value(int(t["volume"] * 100))
        art = t.get("art_path", "")
        p = local_art(art, 512) if art else None
        if p:
            img = image_for(p)
            if img is not None:
                self._cover._img = img
                self._cover.redraw(); self._cover.content_changed()
        elif not self._cover._img:
            self._cover._cover_title = t.get("album") or t.get("title", "")
            self._cover.redraw(); self._cover.content_changed()


class QueuePage(ztos.Page):
    """The queue: rows, current in accent; tap = jumpTo, hold = remove."""

    def __init__(self):
        super().__init__("queue")
        self.list.setContentsMargins(17, 0, 16, 24)
        self.bar(ztos.RoundButton("delete", "clear", self._clear))
        backend.queue_changed.connect(self._maybe_refill)

    def _maybe_refill(self):
        if self.isVisible():
            self.shown()

    def shown(self):
        self.clear()
        items, position = backend.queue_items()
        if not backend.live:
            from hub import Notice
            self.add(Notice(backend.demo_notice or "demo data"))
        for i, it in enumerate(items):
            self.add(Row(rtitle(it), it.get("subtitle", ""), it.get("duration_ms", 0),
                         accent=(i == position),
                         on_tap=lambda i=i: backend.jump_to(i),
                         on_hold=lambda i=i: ztos.menu(self, [
                             ("remove from queue", lambda i=i: backend.remove_from_queue(i))])))

    def _clear(self):
        backend.clear_queue()
        self.shown()


FILTERS = [("all", "all"), ("songs", "songs"), ("albums", "albums"),
           ("artists", "artists"), ("playlists", "playlists")]


class SearchPage(ztos.Page):
    """Search the catalog+library: field on top, results as rows, debounce."""

    def __init__(self):
        super().__init__("search")
        self.list.setContentsMargins(17, 0, 16, 24)
        self._debounce = QTimer(self, singleShot=True, interval=350)
        self._debounce.timeout.connect(self._run)
        self._box = self.textbox("search", placeholder="artist, album, song…",
                                 on_change=lambda _t: self._debounce.start())
        st = ztos.store("zunehd")
        self._filter = st.get("search_filter", "all")
        if self._filter not in dict(FILTERS):
            self._filter = "all"
        self._filter_btn = ztos.RoundButton("more", f"filter: {self._filter}", self._filter_menu)
        self.bar(self._filter_btn)

    def shown(self):
        self._box.field.setFocus(Qt.MouseFocusReason)

    def _filter_menu(self):
        ztos.menu(self, [(f"{label}{'  ✓' if key == self._filter else ''}",
                          (lambda k=key: self._set_filter(k))) for key, label in FILTERS])

    def _set_filter(self, key):
        self._filter = key
        st = ztos.store("zunehd")
        st["search_filter"] = key
        st.save()
        self._filter_btn.set_label(f"filter: {key}")
        self._debounce.start()

    def _run(self):
        q = self._box.text().strip()
        results = backend.search(q, self._filter) if q else []
        while self.list.count() > 2:               # keep field (0) and stretch
            item = self.list.takeAt(1)
            if item.widget() is not None:
                item.widget().deleteLater()
        if q and not results:
            from hub import Notice
            self.list.insertWidget(self.list.count() - 1,
                                   Notice("no results" if backend.live else
                                          (backend.demo_notice or "demo data")))
        for r in results:
            row = Row(rtitle(r), r.get("subtitle", ""), r.get("durationMs", 0),
                      on_tap=(lambda r=r: self._open(r)))
            self.list.insertWidget(self.list.count() - 1, row)

    def _open(self, r):
        import hub
        kind = r.get("kind")
        if kind == "song":
            sid = r.get("catalogId") or r.get("id", "")
            backend.play_ids([sid], 0)
        elif kind in ("album", "artist", "playlist"):
            self._app_push(hub.DetailPage(r.get("pageKind", kind), r.get("id", "")))

    def _app_push(self, page):
        app = ztos.App.current
        app.push(page)


class SettingsPage(ztos.Page):
    """Settings: daemon stage/mode, sign in/out, refresh, quit, about."""

    def __init__(self):
        super().__init__("settings", header=False)
        self._stage = None
        self.entry("sign in", "slipmatd", lambda: backend.sign_in())
        self.entry("sign out", "", lambda: backend.sign_out())
        self.entry("refresh library", "", lambda: backend.refresh())
        self.entry("quit", "stop slipmatd", lambda: backend.quit_daemon())
        self.space(8)
        self._stage_row = self.entry("daemon", "…", on_hold=None)
        self.entry("about", "", self._about)
        backend.stage_changed.connect(lambda _s: self._refresh_stage())
        backend.error.connect(lambda e: ztos.notify("slipmatd", e))
        self._refresh_stage()

    def shown(self):
        self._refresh_stage()

    def _refresh_stage(self):
        if self._stage_row is None:
            return
        mode = "live" if backend.live else "demo"
        stage = backend.stage or ("not running" if backend._client is None else "…")
        self._stage_row.set_detail(f"{mode} — stage: {stage}")

    def _about(self):
        accent = ztos.accent()
        backend_name = "slipmatd (live)" if backend.live else (backend.demo_notice or "demo data")
        ztos.message("about", f"{ztos.manifest().get('name')} v{ztos.manifest().get('version')}\n"
                              f"accent {accent.name()} from ztSettings\nbackend: {backend_name}",
                     ["ok"], lambda _c: None)
