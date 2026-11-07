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
