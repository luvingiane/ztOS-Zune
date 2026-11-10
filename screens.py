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
import icons
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter
from PySide6.QtWidgets import QAbstractSlider

from client import backend, rtitle, unplayable_ids, is_available
from widgets import Row, CircleButton, RowWarmer, ROW_H


GRIP_W = 44


class Grip(QAbstractSlider):
    """Drag handle at the right of a queue row. It subclasses QAbstractSlider
    on purpose: the SDK's finger filter (`_Finger._down`) treats sliders as
    `passive` — it neither scrolls the page nor takes the touch over — so the
    handle receives press/move/release as they are, with no long-press and no
    poking at SDK internals. Emits the GLOBAL y of the finger."""

    grabbed = Signal(float)
    dragged = Signal(float)
    dropped = Signal(float)

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(GRIP_W, ROW_H)
        self._down = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 200 if self._down else 120))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        for dy in (-7, 0, 7):                    # three bars: the usual "reorder" handle
            p.drawRoundedRect(QRectF(cx - 9, cy + dy - 1.5, 18, 3), 1.5, 1.5)

    def mousePressEvent(self, event):
        self._down = True
        self.update()
        self.grabbed.emit(event.globalPosition().y())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._down:
            self.dragged.emit(event.globalPosition().y())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._down:
            self._down = False
            self.update()
            self.dropped.emit(event.globalPosition().y())
        event.accept()


class QueueRow(Row):
    """A queue row with its drag handle pinned to the right edge (re-placed on
    every resize: the row has no final width when it is built)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._right = GRIP_W
        self._grip = Grip(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - GRIP_W, 0)


class QueuePage(ztos.Page):
    """The queue. Rebuilt only when the CONTENT changes (signature of
    id+title), never on position-only events. Rows are TEXT ONLY. Tap =
    jumpTo, hold = menu (remove), drag the handle on the right = reorder
    (moveInQueue, ipc.rs:236-238): the row is lifted and the others make room
    live, the page scrolls itself near its edges."""

    EDGE = 56          # px from the viewport edge where auto-scroll starts

    def __init__(self):
        super().__init__("queue")
        self.list.setContentsMargins(17, 0, 16, 24)
        self.bar(CircleButton(icons.path("clear"), "clear", self._clear))
        self._sig = None
        self._row_widgets = []
        self._drag_row = None
        self._drag_from = None
        self._drag_gy = 0.0
        self._warmer = RowWarmer(self)
        self._scroll_timer = QTimer(self, interval=30)
        self._scroll_timer.timeout.connect(self._autoscroll)
        backend.queue_changed.connect(self._on_queue_event)

    def shown(self):
        self._fill(backend.queue_items())

    def _on_queue_event(self):
        if not self.isVisible() or self._drag_row is not None:
            return                                   # never rebuild under a finger
        items, position = backend.queue_items()
        sig = tuple((i.get("id"), i.get("title")) for i in items)
        if sig == self._sig:
            # position/accent only: repaint accents in place, NO rebuild
            for idx, row in enumerate(self._row_widgets):
                if row._accent != (idx == position):
                    row._accent = (idx == position)
                    # redraw only: content_changed() would mark the page's GL
                    # list picture dirty and re-render the whole body into a
                    # big texture on every queue event (the squash/overlap on B)
                    row.redraw()
            return
        self._fill((items, position))

    def _fill(self, q):
        items, position = q
        self.clear()
        self._row_widgets = []
        self._sig = tuple((i.get("id"), i.get("title")) for i in items)
        if not backend.live:
            from hub import Notice
            self.add(Notice(backend.demo_notice or "demo data"))
        unplay = unplayable_ids()
        for i, it in enumerate(items):
            r = QueueRow(rtitle(it), it.get("subtitle", ""), it.get("duration_ms", 0),
                         accent=(i == position), available=(it.get("id") not in unplay))
            # indices are looked up live: the order changes while dragging
            r.tapped.connect(lambda r=r: backend.jump_to(self._row_widgets.index(r)))
            r.held.connect(lambda r=r: self._row_menu(r))
            grip = r._grip
            grip.grabbed.connect(lambda gy, r=r: self._drag_begin(r, gy))
            grip.dragged.connect(self._drag_move)
            grip.dropped.connect(self._drag_end)
            r._qkey = (it.get("id"), it.get("title"))
            self._row_widgets.append(r)
            self.add(r)
        self._warmer.start()

    def _row_menu(self, row):
        ztos.menu(self, [("remove from queue",
                          lambda: (backend.remove_from_queue(self._row_widgets.index(row)), self.shown()))])

    # ---- drag to reorder ---------------------------------------------------
    def _drag_begin(self, row, gy):
        self._stop()
        self._gl_end()                  # live widget tree while rows move (no stale GL picture)
        self._drag_row = row
        self._drag_from = self._row_widgets.index(row)
        self._drag_gy = gy
        row._lift = True
        row.redraw()
        ztos.haptic("tap")
        self._scroll_timer.start()

    def _drag_move(self, gy):
        self._drag_gy = gy
        row = self._drag_row
        if row is None:
            return
        y = self.body.mapFromGlobal(QPointF(0, gy).toPoint()).y()
        others = [r for r in self._row_widgets if r is not row]
        target = sum(1 for r in others if r.y() + r.height() / 2.0 < y)
        if target != self._row_widgets.index(row):
            base = self.list.indexOf(self._row_widgets[0])
            self._row_widgets.remove(row)
            self._row_widgets.insert(target, row)
            self.list.removeWidget(row)
            self.list.insertWidget(base + target, row)
            ztos.haptic("tick")

    def _autoscroll(self):
        if self._drag_row is None:
            self._scroll_timer.stop()
            return
        vy = self.viewport.mapFromGlobal(QPointF(0, self._drag_gy).toPoint()).y()
        vh = self.viewport.height()
        step = 0.0
        if vy < self.EDGE:
            step = -min(18.0, (self.EDGE - vy) * 0.4 + 3)
        elif vy > vh - self.EDGE:
            step = min(18.0, (vy - (vh - self.EDGE)) * 0.4 + 3)
        if step:
            self.scroll_to(self._scroll + step)
            self._drag_move(self._drag_gy)           # rows moved under the finger

    def _drag_end(self, gy):
        row = self._drag_row
        if row is None:
            return
        self._drag_move(gy)
        self._scroll_timer.stop()
        frm, to = self._drag_from, self._row_widgets.index(row)
        self._drag_row = self._drag_from = None
        row._lift = False
        row.redraw()
        if frm != to:
            backend.move_in_queue(frm, to)
            # keep our signature in step with the new local order: the daemon's
            # queue event then matches and does not rebuild the page
            self._sig = tuple(r._qkey for r in self._row_widgets)
        for idx, r in enumerate(self._row_widgets):
            r.redraw()

    def _clear(self):
        backend.clear_queue()
        self.shown()


FILTERS = [("all", "all"), ("songs", "songs"), ("albums", "albums"),
           ("artists", "artists"), ("playlists", "playlists")]
# result sections, in display order: (entry kind, header, rows shown in "all")
SECTIONS = [("artist", "artists", 3), ("album", "albums", 4), ("song", "songs", 6),
            ("playlist", "playlists", 3)]
KIND_FILTER = {"artist": "artists", "album": "albums", "song": "songs", "playlist": "playlists"}


def group_results(results):
    """Group search entries by kind, in the section order (artists, albums,
    songs, playlists). Returns [(kind, header, [rows])] without empty groups."""
    out = []
    for kind, header, _cap in SECTIONS:
        rows = [r for r in results if r.get("kind") == kind]
        if rows:
            out.append((kind, header, rows))
    return out


class FilterBar(ztos.Entry):
    """The category chips under the search field: all / songs / albums /
    artists / playlists. The selected one is in the accent colour."""

    H = 40

    def __init__(self, current, on_pick):
        super().__init__("", "")
        self._current = current
        self._on_pick = on_pick
        self.setFixedHeight(self.H)
        self._font = ztos._font(ztos.FONT_REGULAR, 15)
        fm = QFontMetricsF(self._font)
        self._spans = []                  # (key, label, x, w)
        x = 0.0
        for key, label in FILTERS:
            w = fm.horizontalAdvance(label)
            self._spans.append((key, label, x, w))
            x += w + 18

    def set_current(self, key):
        self._current = key
        self.redraw()

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.TextAntialiasing)
        p.setFont(self._font)
        for key, label, x, w in self._spans:
            sel = key == self._current
            p.setPen(ztos.accent() if sel else QColor(255, 255, 255, 150))
            p.drawText(QPointF(x, 26), label)
            if sel:
                p.fillRect(QRectF(x, 31, w, 2), ztos.accent())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        x = event.position().x()
        for key, _label, sx, w in self._spans:
            if sx - 9 <= x <= sx + w + 9:
                self._on_pick(key)
                return


class SearchPage(ztos.Page):
    """Search the catalog+library: field + category chips on top, results
    grouped into Artists / Albums / Songs / Playlists (headers, "see all"),
    350 ms debounce. Artist -> artist page (its albums), album/playlist ->
    their page, song -> plays the song results from that row."""

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
        self._chips = FilterBar(self._filter, self._set_filter)
        self.add(self._chips)
        self._fixed = self.list.count()          # field + chips + stretch: kept on refresh
        self._songs = []

    def shown(self):
        self._box.field.setFocus(Qt.MouseFocusReason)

    def _set_filter(self, key):
        self._filter = key
        st = ztos.store("zunehd")
        st["search_filter"] = key
        st.save()
        self._chips.set_current(key)
        self._debounce.start()

    def _clear_results(self):
        while self.list.count() > self._fixed:
            item = self.list.takeAt(self._fixed - 1)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _run(self):
        q = self._box.text().strip()
        results = backend.search(q, self._filter) if q else []
        self._clear_results()
        if q and not results:
            from hub import Notice
            self.add(Notice("no results" if backend.live else (backend.demo_notice or "demo data")))
        self._songs = [r for r in results if r.get("kind") == "song"]
        for kind, header, rows in group_results(results):
            cap = dict((k, c) for k, _h, c in SECTIONS)[kind]
            shown = rows if self._filter != "all" else rows[:cap]
            self.section(header)
            for r in shown:
                self.add(self._make_row(r))
            if self._filter == "all" and len(rows) > cap:
                self.add(Row(f"see all {header}", f"{len(rows)} results",
                             on_tap=lambda k=kind: self._set_filter(KIND_FILTER[k])))

    def _make_row(self, r):
        kind = r.get("kind")
        art = r.get("artworkTemplate", "")
        if kind == "song":
            from hub import song_menu
            return Row(rtitle(r), r.get("subtitle", ""), r.get("durationMs", 0), art=art,
                       available=is_available(r), on_tap=lambda r=r: self._play_song(r),
                       on_hold=lambda r=r: song_menu(self, r))
        return Row(rtitle(r), r.get("subtitle", ""), art=art, on_tap=lambda r=r: self._open(r))

    def _play_song(self, r):
        i = next((k for k, s in enumerate(self._songs) if s is r), 0)
        sent, reason = backend.play_list(self._songs, i)
        if not sent:
            ztos.notify("cannot play", reason or "slipmatd not ready")
            return
        if reason:
            ztos.notify("unavailable", reason)

    def _open(self, r):
        import hub
        kind = r.get("kind")
        if kind in ("album", "artist", "playlist"):
            ztos.App.current.push(hub.DetailPage(r.get("pageKind", kind), r.get("id", ""), rtitle(r)))


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
        st = ztos.store("zunehd")
        self.toggle("Notifiche cambio brano", on=bool(st.get("notify_track", False)),
                    on_change=lambda on: (st.__setitem__("notify_track", on), st.save()))
        self.toggle("Sfondo sfocato nel player", on=bool(st.get("blur_bg", True)),
                    on_change=lambda on: (st.__setitem__("blur_bg", on), st.save()))
        import art as art_mod
        self.toggle("Copertine nelle liste", on=bool(st.get("covers", True)),
                    on_change=lambda on: (st.__setitem__("covers", on), st.save(), art_mod.set_covers(on)))
        self.toggle("Album in lista (senza griglia)", on=bool(st.get("albums_list", False)),
                    on_change=lambda on: (st.__setitem__("albums_list", on), st.save()))
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
