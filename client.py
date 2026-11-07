"""Backend of the app: slipmatd when it answers, demo data otherwise.

Wraps slipmat/ipc.py (the wire client, reused from the phase-2 project): one
subscribed connection; `browse` answers arrive as `rows` events, `search` as
`results`, plus pushed `snapshot`/`queue`/`stage` events. When the socket is
not there (or the daemon does not answer in time) every call falls back to
library.py's demo data, so the UI is always the same.
"""
import threading

import library

_VIEWS = ("artists", "albums", "songs", "playlists")


class Backend:
    def __init__(self):
        self._client = None
        self._tried = False
        self._lock = threading.Lock()
        self._rows = {}          # view -> [dict]  (entry_to_dict)
        self._results = {}       # query -> [dict]
        self._wait = threading.Event()
        self.snapshot = None     # last `snapshot` event (flat track)
        self.queue = None        # last `queue` event {items, position}
        self.stage = None

    @property
    def live(self) -> bool:
        return self._client is not None

    def connect(self, timeout=2.0) -> bool:
        """Connect once (and subscribe); False when slipmatd is not there."""
        if self._client is not None:
            return True
        if self._tried or not library.slipmat_available():
            self._tried = True
            return False
        self._tried = True
        try:
            from slipmat.ipc import SlipmatClient
            client = SlipmatClient()
            client.eventReceived.connect(self._on_event)
            client.subscribe()
            client.stage()
            client.snapshot()
            client.queue()
            self._client = client
            return True
        except Exception:
            self._client = None
            return False

    def _on_event(self, ev):
        from slipmat.ipc import entry_to_dict
        tag = ev.get("event", "")
        if tag == "rows":
            with self._lock:
                self._rows[ev.get("view", "")] = [entry_to_dict(e) for e in ev.get("entries", [])]
            self._wait.set()
        elif tag == "results":
            with self._lock:
                self._results[ev.get("query", "")] = [entry_to_dict(e) for e in ev.get("entries", [])]
            self._wait.set()
        elif tag == "snapshot":
            self.snapshot = ev
        elif tag == "queue":
            self.queue = ev
        elif tag == "stage":
            self.stage = ev.get("stage")

    # ---- reads ---------------------------------------------------------------
    def browse(self, view, timeout=1.5):
        """Rows of a collection view ('artists'/'albums'/'songs'/'playlists')."""
        if view not in _VIEWS:
            return []
        if self.connect():
            self._wait.clear()
            self._client.browse(view, limit=500)
            self._wait.wait(timeout)
            with self._lock:
                rows = self._rows.get(view)
            if rows is not None:
                return rows
        return library.demo_library()[view]

    def search(self, query, timeout=1.5):
        if self.connect() and query:
            self._wait.clear()
            self._client.search(query)
            self._wait.wait(timeout)
            with self._lock:
                rows = self._results.get(query)
            if rows is not None:
                return rows
        q = query.lower()
        out = []
        for view in _VIEWS:
            for row in library.demo_library()[view]:
                title = row.get("title") or row.get("name") or ""
                if q in title.lower() or q in row.get("subtitle", "").lower():
                    out.append(row)
        return out

    def now_playing(self):
        s = self.snapshot or {}
        if self.live and s:
            return {"title": s.get("title", ""), "artist": s.get("artist", ""),
                    "album": s.get("album", ""), "duration_ms": s.get("duration_ms", 0),
                    "position_ms": s.get("position_ms", 0), "playing": bool(s.get("playing"))}
        return dict(library.NOW_PLAYING)

    def queue_items(self):
        if self.live and self.queue:
            items = []
            for it in self.queue.get("items", []):
                items.append({"id": it.get("id", ""), "title": it.get("title", ""),
                              "subtitle": f"{it.get('artist', '')} — {it.get('album', '')}",
                              "duration_ms": it.get("duration_ms", 0)})
            return items, self.queue.get("position", 0)
        demo = library.demo_library()["songs"]
        return demo[:6], 0

    # ---- writes (no-ops on demo data) ----------------------------------------
    def _send(self, fn, *a, **k):
        if self.connect():
            return fn(*a, **k)
        return False

    def play_ids(self, ids, index=0):
        return self._send(self._client.play, ids, index) if self.live else False

    def enqueue(self, ids, next_=False):
        return self._send(self._client.enqueue, ids, next_) if self.live else False

    def transport(self, cmd, **fields):
        return self._send(self._client.transport, cmd, **fields) if self.live else False

    def seek(self, position_ms):
        return self.transport("seek", position_ms=int(position_ms))

    def jump_to(self, index):
        return self._send(self._client.jump_to, index) if self.live else False

    def remove_from_queue(self, index):
        return self._send(self._client.remove_from_queue, index) if self.live else False

    def clear_queue(self):
        return self._send(self._client.clear_queue) if self.live else False

    def refresh(self):
        return self._send(self._client.refresh) if self.live else False

    def sign_in(self):
        return self._send(self._client.sign_in) if self.live else False

    def sign_out(self):
        return self._send(self._client.sign_out) if self.live else False

    def quit_daemon(self):
        return self._send(self._client.quit) if self.live else False


backend = Backend()
