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
from PySide6.QtCore import Qt, QTimer

from client import backend, rtitle
from widgets import Row


def _art_for(title: str, subtitle: str) -> str:
    """Artwork template of a queue row: queue items carry no artwork, so look
    the track up in the cached songs rows (by title + artist)."""
    with backend._lock:
        rows = backend._rows.get("songs")
    if rows:
        artist = subtitle.split(" — ")[0] if subtitle else ""
        for r in rows:
            if r.get("title") == title and (not artist or r.get("artist") == artist):
                return r.get("artworkTemplate", "")
    return ""


class QueuePage(ztos.Page):
    """The queue. Rebuilt only when the CONTENT changes (signature of
    id+title), never on position-only events — a queue event storm used to
    freeze the page. Rows: tap = jumpTo, hold = remove, long-press + drag =
    reorder (moveInQueue, ipc.rs:236-238)."""

    def __init__(self):
        super().__init__("queue")
        self.list.setContentsMargins(17, 0, 16, 24)
        self.bar(ztos.RoundButton("delete", "clear", self._clear))
        self._sig = None
        self._row_widgets = []
        self._drag_from = None
        self._drag_over = None
        backend.queue_changed.connect(self._on_queue_event)

    def shown(self):
        self._fill(backend.queue_items())

    def _on_queue_event(self):
        if not self.isVisible():
            return
        items, position = backend.queue_items()
        sig = tuple((i.get("id"), i.get("title")) for i in items)
        if sig == self._sig:
            # position/accent only: repaint accents in place, NO rebuild
            for idx, row in enumerate(self._row_widgets):
                if row._accent != (idx == position):
                    row._accent = (idx == position)
                    row.redraw()
                    row.content_changed()
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
        for i, it in enumerate(items):
            r = Row(rtitle(it), it.get("subtitle", ""), it.get("duration_ms", 0),
                    art=_art_for(it.get("title", ""), it.get("subtitle", "")),
                    accent=(i == position),
                    on_tap=lambda i=i: backend.jump_to(i),
                    on_hold=lambda i=i: self._start_drag(i))
            r.installEventFilter(self)
            self._row_widgets.append(r)
            self.add(r)

    # ---- drag to reorder ---------------------------------------------------
    def _start_drag(self, index):
        # long-press: enter reorder mode; let mouse moves reach the rows
        # (the SDK finger filter would otherwise eat them as a scroll)
        self._drag_from = index
        self._drag_over = index
        try:
            ztos.App.current._finger.active = False
        except Exception:
            pass
        ztos.haptic("tap")

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        # NB: Qt can call eventFilter during QWidget.__init__, before our
        # attributes exist — always getattr-guard here
        if getattr(self, "_drag_from", None) is not None:
            if event.type() == QEvent.MouseMove:
                y = obj.y() + event.position().y()
                idx = max(0, min(len(self._row_widgets) - 1, int(y // 71)))
                if idx != self._drag_over:
                    self._drag_over = idx
                    for i, r in enumerate(self._row_widgets):
                        hl = (i == self._drag_over)
                        if r._accent != hl:
                            r._accent = hl
                            r.redraw()
                            r.content_changed()
            elif event.type() == QEvent.MouseButtonRelease:
                frm, to = self._drag_from, self._drag_over
                self._drag_from = None
                self._drag_over = None
                try:
                    ztos.App.current._finger.active = True
                except Exception:
                    pass
                if frm is not None and to is not None and frm != to:
                    backend.move_in_queue(frm, to)
                    self.shown()
        return False

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
                      art=r.get("artworkTemplate", ""),
                      on_tap=(lambda r=r: self._open(r)))
            self.list.insertWidget(self.list.count() - 1, row)

    def _open(self, r):
        import hub
        kind = r.get("kind")
        if kind == "song":
            sid = r.get("catalogId") or ""
            if not sid:
                ztos.notify("cannot play", "this track cannot be streamed (catalog_id is null)")
            else:
                backend.play_ids([sid], 0)
        elif kind in ("album", "artist", "playlist"):
            self._app_push(hub.DetailPage(r.get("pageKind", kind), r.get("id", ""), rtitle(r)))

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
        st = ztos.store("zunehd")
        self.toggle("Notifiche cambio brano", on=bool(st.get("notify_track", False)),
                    on_change=lambda on: (st.__setitem__("notify_track", on), st.save()))
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
