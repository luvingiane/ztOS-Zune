"""Backend of the app: slipmatd when it is ready, an empty state otherwise.

Wraps slipmat/ipc.py (the wire client): one subscribed connection; `browse`
answers arrive as `rows` events, `search` as `results`, `open` as `page`, plus
pushed `snapshot`/`queue`/`stage`/`libraryChanged`/`error` events.

Mode rule (owner, 7/11): with stage == "ready" ONLY the daemon's data is
used; when the daemon is missing or its stage is signedOut/broken the pages
are empty with a visible notice (see `status_notice`). There is no sample data.

Sort: the daemon sorts (`browse` sort/reverse, SortBy in
slipmat-core/src/sort.rs) for every view; songs have no "added" (Apple sends
no dateAdded for library songs — measured 0/541 in music/types.rs:366-373),
so for songs+"added" we join the albums' date_added client-side and sort by
(album added, track number) — the closest Apple's data allows.
"""
import os
import subprocess
import threading
import time

from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Signal, Slot

import library


class _ParseWorker(QObject):
    """Parses daemon payloads (entry_to_dict over hundreds of rows) OFF the GUI
    thread; results come back as queued signals."""
    ask_rows = Signal(str, list)
    ask_page = Signal(str, str, object, list)
    rows_done = Signal(str, list)
    page_done = Signal(str, str, object, list)

    def __init__(self):
        super().__init__()
        self._t = QThread()
        self.moveToThread(self._t)
        self.ask_rows.connect(self._do_rows)
        self.ask_page.connect(self._do_page)
        self._t.start()

    @Slot(str, list)
    def _do_rows(self, view, raw_entries):
        from slipmat.ipc import entry_to_dict
        self.rows_done.emit(view, [entry_to_dict(e) for e in raw_entries])

    @Slot(str, str, object, list)
    def _do_page(self, kind, id_, header, raw_entries):
        from slipmat.ipc import entry_to_dict
        self.page_done.emit(kind, id_, entry_to_dict(header),
                            [entry_to_dict(e) for e in raw_entries])


def _pump_wait(ev, timeout):
    """Wait on a threading.Event while keeping Qt's event loop running: the
    daemon's answers arrive as queued signals on THIS thread, so a plain
    ev.wait() would deadlock the loop and time out (that is why live rows
    used to time out on the phone)."""
    app = QCoreApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if ev.wait(0.05):
            return True
    return ev.is_set()


def rtitle(r) -> str:
    """Main text of a row: entry_to_dict flattens to "title", some
    rows keep "name" for artists/albums/playlists."""
    return r.get("title") or r.get("name") or ""

VIEWS = ("artists", "albums", "songs", "playlists")

# Songs the daemon found unplayable at runtime: a JSON array of catalog ids in
# ~/.cache/slipmat/unplayable.json (read on B 10/11: ["1021729324", ...]).
# Together with catalog_id == None they are the "not available" rows.
_UNPLAYABLE = {"mtime": None, "ids": frozenset()}


def unplayable_ids():
    import json
    path = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                        "slipmat", "unplayable.json")
    try:
        m = os.stat(path).st_mtime
    except OSError:
        _UNPLAYABLE.update(mtime=None, ids=frozenset())
        return _UNPLAYABLE["ids"]
    if m != _UNPLAYABLE["mtime"]:
        try:
            with open(path) as f:
                _UNPLAYABLE.update(mtime=m, ids=frozenset(str(x) for x in json.load(f)))
        except (OSError, ValueError):
            _UNPLAYABLE.update(mtime=m, ids=frozenset())
    return _UNPLAYABLE["ids"]


def is_available(row) -> bool:
    """False for a song that cannot be streamed: no catalog id, or the daemon
    already learned it fails (unplayable.json). Non-song rows are available."""
    if row.get("kind", "song") != "song":
        return True
    cid = row.get("catalogId") or row.get("catalog_id") or ""
    if not cid:
        # rows without the daemon's raw payload (never from the daemon) are not judged
        return not row.get("raw")
    return cid not in unplayable_ids()


# SortBy::for_view (slipmat-core/src/sort.rs:53-60): what each list can sort by.
# songs also offers "added" (owner requirement): Apple sends no dateAdded for
# library songs, so client.browse joins the albums' date_added (see there).
SORTS = {
    "songs": ["title", "artist", "album", "year", "added"],
    "albums": ["title", "artist", "year", "added"],
    "playlists": ["title", "added", "updated"],
    "artists": ["title"],
}
SORT_LABELS = {"title": "title", "artist": "artist", "album": "album", "year": "year",
               "added": "recently added", "updated": "recently updated"}
# SortBy::descends_by_default (sort.rs): dates read newest-first
SORT_DESC_DEFAULT = {"year", "added", "updated"}


class Backend(QObject):
    changed = Signal()            # libraryChanged: refill the visible page
    stage_changed = Signal(str)
    snapshot_changed = Signal()
    queue_changed = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._client = None
        self._lock = threading.Lock()
        self._events = {}         # key -> threading.Event
        self._rows = {}           # view -> [dict]
        self._results = {}        # query -> [dict]
        self._pages = {}          # (kind, id) -> (header, entries)
        self.snapshot = None
        self.queue = None
        self.stage = None
        self.last_error = ""
        self._starting = False    # one daemon-start attempt at a time
        self._reconnect_pending = False
        self._backoff = 2.0
        self._pending_rows = {}    # view -> [(sort, reverse, cb)]
        self._pending_results = {}
        self._pending_pages = {}   # (kind, id) -> [cb]
        self._parser = _ParseWorker()
        self._parser.rows_done.connect(self._rows_parsed)
        self._parser.page_done.connect(self._page_parsed)

    # ---- connection / mode ---------------------------------------------------
    @property
    def live(self) -> bool:
        """True only when the daemon is connected AND stage == ready."""
        return self._client is not None and self.stage == "ready"

    @property
    def status_notice(self):
        """Why there is nothing to show (empty when the daemon is ready)."""
        if self._client is None:
            return "slipmatd not running"
        if self.stage and self.stage != "ready":
            return f"slipmatd stage: {self.stage}"
        return ""

    # ---- daemon lifecycle: socket -> systemctl --user -> /usr/bin/slipmatd --
    def _socket_path(self):
        from slipmat.ipc import socket_path
        return socket_path()

    def _wait_socket(self, path, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path and os.path.exists(path):
                return True
            _pump_wait(threading.Event(), 0.1)
        return bool(path and os.path.exists(path))

    def _ensure_daemon(self) -> bool:
        """Make sure slipmatd is listening, without blocking the GUI (events
        keep being pumped while waiting) and with one start attempt at a time.
        Order: existing socket, `systemctl --user start slipmatd`, then
        `/usr/bin/slipmatd` by absolute path (never trust PATH)."""
        path = self._socket_path()
        if path and os.path.exists(path):
            return True
        if not path:
            return False
        if self._starting:
            return False
        self._starting = True
        try:
            try:
                subprocess.Popen(["systemctl", "--user", "start", "slipmatd"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                if self._wait_socket(path, 5.0):
                    return True
            except OSError:
                pass
            if os.path.exists("/usr/bin/slipmatd"):
                subprocess.Popen(["/usr/bin/slipmatd"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                return self._wait_socket(path, 8.0)
            self.last_error = "slipmatd not found (no socket, no systemctl unit, no /usr/bin/slipmatd)"
            return False
        finally:
            self._starting = False

    def _schedule_reconnect(self):
        """Auto-reconnect with backoff (2s, 4s, ... max 30s), one pending."""
        if self._reconnect_pending:
            return
        self._reconnect_pending = True
        QTimer.singleShot(int(self._backoff * 1000), self._reconnect)

    def _reconnect(self):
        self._reconnect_pending = False
        self._backoff = min(30.0, self._backoff * 2)
        if self._client is None:
            self.stage = None
            self.stage_changed.emit("reconnecting…")
            self.connect()

    def connect(self, ready_timeout=3.0) -> bool:
        """Connect once, subscribe, and wait briefly for the stage event.
        The stage also arrives later as an event and updates the UI itself."""
        if self._client is not None:
            return self.live
        if not self._ensure_daemon():
            return False
        try:
            from slipmat.ipc import SlipmatClient
            client = SlipmatClient()          # socket exists: no spawn, no 10s block
            client.eventReceived.connect(self._on_event)
            def _lost(why):
                self.error.emit(f"slipmatd connection lost: {why}")
                self._client = None
                self.stage = None
                self._backoff = 2.0
                self.stage_changed.emit("reconnecting…")
                self._schedule_reconnect()
            client.lost.connect(_lost)
            self._client = client
            self._backoff = 2.0
            client.subscribe()
            client.stage()
            client.snapshot()
            client.queue()
            deadline = time.monotonic() + ready_timeout
            while self.stage is None and time.monotonic() < deadline:
                _pump_wait(self._events.setdefault("stage", threading.Event()), 0.1)
            return self.live
        except Exception as exc:
            self.last_error = str(exc)
            self._client = None
            self._schedule_reconnect()
            return False

    def _wait_for(self, key, timeout):
        ev = self._events.setdefault(key, threading.Event())
        return _pump_wait(ev, timeout)

    def _rows_parsed(self, view, rows):
        with self._lock:
            self._rows[view] = rows
            pending = self._pending_rows.pop(view, [])
        self._events.setdefault(f"rows:{view}", threading.Event()).set()
        for _sort, _rev, cb in pending:
            try:
                cb(rows)
            except Exception:
                pass

    def _page_parsed(self, kind, id_, header, entries):
        key = (kind, id_)
        with self._lock:
            self._pages[key] = (header, entries)
            pending = self._pending_pages.pop(key, [])
        self._events.setdefault(f"page:{key}", threading.Event()).set()
        for cb in pending:
            try:
                cb(header, entries)
            except Exception:
                pass

    def _on_event(self, ev):
        tag = ev.get("event", "")
        if tag == "rows":
            view = ev.get("view", "")
            self._parser.ask_rows.emit(view, ev.get("entries", []))   # parse off the GUI thread
        elif tag == "results":
            from slipmat.ipc import entry_to_dict
            q = ev.get("query", "")
            with self._lock:
                self._results[q] = [entry_to_dict(e) for e in ev.get("entries", [])]
            self._events.setdefault(f"results:{q}", threading.Event()).set()
            with self._lock:
                cbs = self._pending_results.pop(q, [])
                rows = self._results.get(q, [])
            for cb in cbs:
                try:
                    cb(rows)
                except Exception:
                    import traceback
                    traceback.print_exc()
        elif tag == "page":
            self._parser.ask_page.emit(ev.get("kind", ""), ev.get("id", ""),
                                   ev.get("header", {}), ev.get("entries", []))
        elif tag == "snapshot":
            prev = self.snapshot or {}
            self.snapshot = ev
            self.snapshot_changed.emit()
            # track-change notification — OFF by default, toggle in Settings
            # (the original's key is notify-track-change in its settings file,
            #  slipmat/src/settings.rs:122,191,222-223; ours: ztos.store)
            if prev and ev.get("title") and ev.get("title") != prev.get("title"):
                try:
                    import ztos
                    if ztos.store("zunehd").get("notify_track", False):
                        ztos.notify(ev.get("title", ""),
                                    f"{ev.get('artist', '')} — {ev.get('album', '')}".strip(" —"))
                except Exception:
                    pass
            # live tile (ztmetro/TILE-SIGNALS.md): key = app id, file
            # $XDG_RUNTIME_DIR/ztos-live/<id>, atomic replace
            try:
                import ztos
                if ev.get("title"):
                    dur = ev.get("duration_ms") or 0
                    pos = ev.get("position_ms") or 0
                    art = ev.get("art_path") or ""
                    ztos.tile_update("Playing" if ev.get("playing") else "Paused",
                                     [ev.get("title", ""), ev.get("artist", "")],
                                     image=art if art and os.path.exists(art) else "",
                                     progress=int(100 * pos / dur) if dur else 0,
                                     badge="play" if ev.get("playing") else "pause")
                else:
                    ztos.tile_clear()
            except Exception:
                pass
        elif tag == "queue":
            self.queue = ev
            self.queue_changed.emit()
        elif tag == "stage":
            self.stage = ev.get("stage", "")
            self._events.setdefault("stage", threading.Event()).set()
            self.stage_changed.emit(self.stage)
        elif tag == "libraryChanged":
            with self._lock:
                self._rows.clear()
            self.changed.emit()
        elif tag == "error":
            self.last_error = ev.get("detail", "")
            self.error.emit(self.last_error)

    # ---- reads ---------------------------------------------------------------
    def browse(self, view, sort="title", reverse=False, timeout=8.0):
        """Rows of a collection view, sorted. Live: the daemon sorts — except
        songs+"added", which Apple's data does not have (no dateAdded on
        library songs), so those are joined client-side through the albums'
        date_added. When live, a timeout returns []; without the daemon it is [] too.

        `reverse` flips the natural direction (dates are newest-first by
        default — SortBy::descends_by_default, sort.rs)."""
        if view not in VIEWS:
            return []
        if sort not in SORTS[view]:
            sort = SORTS[view][0]
        desc = (sort in SORT_DESC_DEFAULT) != bool(reverse)
        if self.connect() and self.live:
            if view == "songs" and sort == "added":
                rows = self._live_rows("songs", "title", False, timeout) or []
                albums = self._live_rows("albums", "added", True, timeout) or []
                added = {a["title"]: a["dateAdded"] for a in albums if a.get("dateAdded")}
                rows.sort(key=lambda s: (added.get(s.get("album", ""), ""),
                                         (s.get("raw") or {}).get("track_number", 0)),
                          reverse=desc)
                return rows
            return self._live_rows(view, sort, reverse, timeout) or []
        return []

    def browse_async(self, view, sort="title", reverse=False, cb=None):
        """Like browse(), but never blocks: cb(rows) is called on the GUI thread
        when the daemon answers (or immediately with [] when not live).
        Pages show their title + 'loading…' first and fill when data arrives."""
        if cb is None or view not in VIEWS:
            return
        if sort not in SORTS[view]:
            sort = SORTS[view][0]
        desc = (sort in SORT_DESC_DEFAULT) != bool(reverse)
        if not (self.connect() and self.live):
            cb([])
            return
        if view == "songs" and sort == "added":
            def got_albums(albums):
                def got_songs(songs):
                    added = {a["title"]: a["dateAdded"] for a in albums if a.get("dateAdded")}
                    songs.sort(key=lambda s: (added.get(s.get("album", ""), ""),
                                              (s.get("raw") or {}).get("track_number", 0)),
                               reverse=desc)
                    cb(songs)
                self.browse_async("songs", "title", False, got_songs)
            self.browse_async("albums", "added", True, got_albums)
            return
        key = f"rows:{view}"
        self._events.setdefault(key, threading.Event()).clear()
        with self._lock:
            self._pending_rows.setdefault(view, []).append((sort, reverse, cb))
        self._client.browse(view, limit=0, sort=sort, reverse=reverse)

    def open_page_async(self, kind, id_, cb):
        """open_page without blocking: cb(header, entries) on the GUI thread."""
        if not (self.connect() and self.live):
            cb({}, [])
            return
        key = (kind, id_)
        ev = f"page:{key}"
        self._events.setdefault(ev, threading.Event()).clear()
        with self._lock:
            self._pending_pages.setdefault(key, []).append(cb)
        self._client.open_page(kind, id_)

    def _live_rows(self, view, sort, reverse, timeout):
        key = f"rows:{view}"
        self._events.setdefault(key, threading.Event()).clear()
        self._client.browse(view, limit=0, sort=sort, reverse=reverse)
        self._wait_for(key, timeout)
        with self._lock:
            return self._rows.get(view)

    def open_page(self, kind, id_, timeout=8.0):
        """(header, entries) of an album/artist/playlist page (`open` req).
        Live timeout -> (None, [])."""
        if self.connect() and self.live:
            key = (kind, id_)
            ev = f"page:{key}"
            self._events.setdefault(ev, threading.Event()).clear()
            self._client.open_page(kind, id_)
            self._wait_for(ev, timeout)
            with self._lock:
                page = self._pages.get(key)
            return page if page is not None else (None, [])
        return {}, []

    def search(self, query, filter_="all", offset=0, timeout=8.0):
        """Catalog+library search. Live timeout -> []."""
        if self.connect() and self.live and query:
            key = f"results:{query}"
            self._events.setdefault(key, threading.Event()).clear()
            self._client.search(query, filter_, offset)
            self._wait_for(key, timeout)
            with self._lock:
                rows = self._results.get(query)
            return rows if rows is not None else []
        return []

    def search_async(self, query, filter_, cb):
        """search without blocking the GUI: cb(rows) when the results arrive."""
        if not (self.connect() and self.live and query):
            cb(self.search(query, filter_))
            return
        with self._lock:
            self._pending_results.setdefault(query, []).append(cb)
        self._client.search(query, filter_, 0)

    def now_playing(self):
        s = self.snapshot or {}
        if self.live and s:
            return {"title": s.get("title", ""), "artist": s.get("artist", ""),
                    "album": s.get("album", ""), "duration_ms": s.get("duration_ms", 0),
                    "position_ms": s.get("position_ms", 0), "playing": bool(s.get("playing")),
                    "art_path": s.get("art_path", ""), "volume": s.get("volume", 1.0),
                    "shuffle": bool(s.get("shuffle", False)), "repeat": s.get("repeat", "none")}
        return {"title": "", "artist": "", "album": "", "duration_ms": 0,
                "position_ms": 0, "playing": False, "art_path": "", "volume": 1.0,
                "shuffle": False, "repeat": "none"}

    def queue_items(self):
        if self.live and self.queue:
            items = [{"id": it.get("id") or "", "title": it.get("title", ""),
                      "subtitle": f"{it.get('artist', '')} — {it.get('album', '')}",
                      "duration_ms": it.get("duration_ms", 0)}
                     for it in self.queue.get("items", [])]
            return items, self.queue.get("position", 0)
        return [], 0

    # ---- writes --------------------------------------------------------------
    def _send(self, fn, *a, **k):
        if self._client is not None and self.live:
            return fn(*a, **k)
        return False

    def play_ids(self, ids, index=0):
        return self._send(self._client.play, ids, index) if self.live else False

    def play_list(self, rows, index):
        """Play a list from a tapped row, exactly like the original client
        (slipmat/src/app/queue.rs play_entries + climat main.rs row click):
        ids = the CATALOG ids of all rows (library ids are dropped — a library
        id is not streamable), index = position among the sendable rows,
        start = "clicked". Returns (sent, reason-if-not)."""
        ok = [is_available(r) and bool(r.get("catalogId")) for r in rows]
        ids = [r.get("catalogId") for r, good in zip(rows, ok) if good]
        if not ids:
            return False, "nothing here can be streamed"
        note = None
        if not ok[index]:
            # tapped an unavailable row: start from the next available one
            nxt = next((i for i in range(index + 1, len(rows)) if ok[i]), None)
            if nxt is None:
                return False, "this track is not available for streaming"
            index, note = nxt, "this track is not available, playing the next one"
        idx = sum(1 for g in ok[:index] if g)
        sent = self._send(self._client.play, ids, idx, "clicked") if self.live else False
        return sent, note if sent else "not live"

    def enqueue(self, ids, next_=False):
        return self._send(self._client.enqueue, ids, next_) if self.live else False

    def transport(self, cmd, **fields):
        return self._send(self._client.transport, cmd, **fields) if self.live else False

    def seek(self, position_ms):
        return self.transport("seek", position_ms=int(position_ms))

    def set_volume(self, volume):
        return self.transport("setVolume", volume=float(volume))

    def set_shuffle(self, on):
        return self.transport("setShuffle", shuffle=bool(on))

    def set_repeat(self, mode):
        return self.transport("setRepeat", mode=mode)

    def jump_to(self, index):
        return self._send(self._client.jump_to, index) if self.live else False

    def remove_from_queue(self, index):
        return self._send(self._client.remove_from_queue, index) if self.live else False

    def move_in_queue(self, from_, to):
        return self._send(self._client.move_in_queue, from_, to) if self.live else False

    def clear_queue(self):
        return self._send(self._client.clear_queue) if self.live else False

    def write(self, action, id_):
        """favorite / unfavorite / addToLibrary / removeFromLibrary (WriteAction)."""
        return self._send(self._client.write, action, id_) if self.live else False

    def refresh(self):
        return self._send(self._client.refresh) if self.live else False

    def sign_in(self):
        return self._send(self._client.sign_in) if self.live else False

    def sign_out(self):
        return self._send(self._client.sign_out) if self.live else False

    def quit_daemon(self):
        try:
            import ztos
            ztos.tile_clear()
        except Exception:
            pass
        return self._send(self._client.quit) if self.live else False


backend = Backend()
