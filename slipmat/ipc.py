"""Client for the slipmatd unix socket — newline-delimited JSON.

Protocol as read from Slipmat 0.12.0 (see IPC.md for file:line citations):
socket $XDG_RUNTIME_DIR/slipmat.sock; one JSON object per line each way;
requests are `{"req": ...}` (camelCase tags), events `{"event": ...}`.
One connection is a stream: send requests, receive events, nothing is paired
(climat/src/link.rs:5-11). On connect we send subscribe/stage/snapshot/queue
(link.rs:96-101).
"""
import json
import os
import socket
import subprocess
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal


def socket_path():
    d = os.environ.get("XDG_RUNTIME_DIR", "")
    if not d:
        return None
    return os.path.join(d, "slipmat.sock")


def art_url(template, size):
    """Artwork template -> concrete CDN URL (mzstatic is public, no token).
    Mirrors Artwork::url() in slipmat-core/src/music/types.rs:107-113."""
    if not template:
        return ""
    s = str(size)
    return (template.replace("{w}", s).replace("{h}", s)
            .replace("{f}", "jpg").replace("{c}", "bb"))


def entry_to_dict(e, art_size=300):
    """Normalize an Entry (tagged `kind`) into a flat dict for the UI.
    Mirrors Entry::subtitle()/page_target() in slipmat-core/src/entry.rs:44-99.
    Keeps the raw entry under "raw" and the artwork template under
    "artworkTemplate" (resolved+cached by art.py, never fetched inline)."""
    kind = e.get("kind", "")
    d = {"kind": kind, "raw": e, "artUrl": "", "artworkTemplate": "", "pageKind": "",
         "playable": False, "id": "", "catalogId": "", "libraryId": "",
         "title": "", "subtitle": "", "durationMs": 0, "dateAdded": "", "year": "",
         "trackCount": 0, "curator": "", "artPath": "", "favorite": False,
         "inLibrary": False, "library": False, "album": "", "artist": ""}
    art = e.get("artwork")
    if art:
        d["artworkTemplate"] = art if isinstance(art, str) else str(art)
        d["artUrl"] = art_url(d["artworkTemplate"], art_size)
    if kind == "song":
        t = e
        d["id"] = t.get("id", "")
        d["catalogId"] = t.get("catalog_id") or ""
        d["libraryId"] = t.get("library_id") or ""
        d["title"] = t.get("title", "")
        artist, album = t.get("artist", ""), t.get("album", "")
        d["artist"], d["album"] = artist, album
        if artist and album:
            d["subtitle"] = f"{artist} — {album}"
        else:
            d["subtitle"] = artist or album
        d["durationMs"] = t.get("duration_ms", 0)
        d["dateAdded"] = t.get("date_added", "")     # empty for library songs (Apple does not send it)
        d["year"] = t.get("year", "")
        d["favorite"] = bool(t.get("favorite", False))
        d["inLibrary"] = bool(t.get("in_library", False))
        d["playable"] = bool(t.get("catalog_id"))
        d["pageKind"] = "song"
    elif kind == "album":
        a = e
        d["id"] = a.get("id", "")
        d["title"] = a.get("name", "")
        artist, year = a.get("artist", ""), a.get("year", "")
        d["artist"], d["year"] = artist, year
        d["subtitle"] = f"{artist} · {year}" if artist and year else (artist or year)
        d["dateAdded"] = a.get("date_added", "")
        d["trackCount"] = a.get("track_count", 0)
        d["library"] = bool(a.get("library", False))
        d["pageKind"] = "libraryAlbum" if d["library"] else "album"
    elif kind == "artist":
        a = e
        d["id"] = a.get("id", "")
        d["title"] = a.get("name", "")                # the artist's NAME is the main text
        d["subtitle"] = a.get("genres", "")           # genres are secondary
        d["library"] = bool(a.get("library", False))
        d["pageKind"] = "libraryArtist" if d["library"] else "artist"
    elif kind == "playlist":
        p = e
        d["id"] = p.get("id", "")
        d["title"] = p.get("name", "")
        d["curator"] = p.get("curator", "")
        d["subtitle"] = d["curator"]
        d["dateAdded"] = p.get("date_added", "")
        d["library"] = bool(p.get("library", False))
        d["pageKind"] = "libraryPlaylist" if d["library"] else "playlist"
    return d


class _Reader(QThread):
    gotLine = Signal(str)
    ended = Signal(str)

    def __init__(self, stream, parent=None):
        super().__init__(parent)
        self._stream = stream
        self._stop = False

    def run(self):
        try:
            f = self._stream.makefile("rb")
            while not self._stop:
                line = f.readline()
                if not line:
                    self.ended.emit("the daemon closed the connection")
                    return
                self.gotLine.emit(line.decode("utf-8", "replace"))
        except OSError as exc:
            self.ended.emit(str(exc))

    def stop(self):
        self._stop = True
        try:
            self._stream.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._stream.close()
        except OSError:
            pass


class SlipmatClient(QObject):
    """One subscribed connection to slipmatd. Thread-safe send()."""

    eventReceived = Signal(dict)
    lost = Signal(str)

    def __init__(self, daemon_exe="slipmatd", parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._stream = None
        self._reader = None
        path = socket_path()
        if path is None:
            raise RuntimeError("XDG_RUNTIME_DIR is not set, nowhere to put the socket")
        try:
            self._stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._stream.connect(path)
        except OSError:
            # No daemon listening: start one (its own session, like
            # connect_or_spawn in ipc.rs:48-108) and wait for the socket.
            subprocess.Popen([daemon_exe], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    self._stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self._stream.connect(path)
                    break
                except OSError:
                    if self._stream:
                        try:
                            self._stream.close()
                        except OSError:
                            pass
                        self._stream = None
                    time.sleep(0.05)
            if self._stream is None:
                raise RuntimeError("the daemon did not start listening")
        self._reader = _Reader(self._stream, self)
        self._reader.gotLine.connect(self._on_line)
        self._reader.ended.connect(self.lost)
        self._reader.start()

    def _on_line(self, line):
        line = line.strip()
        if not line:
            return
        try:
            self.eventReceived.emit(json.loads(line))
        except json.JSONDecodeError:
            self.lost.emit("cannot read the daemon: bad JSON line")

    def send(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        with self._lock:
            if self._stream is None:
                return False
            try:
                self._stream.sendall(data)
                return True
            except OSError:
                return False

    # -- request helpers (wire names from ipc.rs) ---------------------------
    def subscribe(self):
        return self.send({"req": "subscribe"})

    def transport(self, cmd, **fields):
        return self.send({"req": "transport", "cmd": cmd, **fields})

    def jump_to(self, index):
        return self.send({"req": "jumpTo", "index": index})

    def snapshot(self):
        return self.send({"req": "snapshot"})

    def queue(self):
        return self.send({"req": "queue"})

    def stage(self):
        return self.send({"req": "stage"})

    def browse(self, view, query="", offset=0, limit=0, sort="title", reverse=False):
        return self.send({"req": "browse", "view": view, "query": query,
                          "offset": offset, "limit": limit, "sort": sort,
                          "reverse": reverse})

    def search(self, query, filter_="all", offset=0):
        return self.send({"req": "search", "query": query, "filter": filter_,
                          "offset": offset})

    def open_page(self, kind, id_):
        return self.send({"req": "open", "kind": kind, "id": id_})

    def play(self, ids, index=0, start="clicked"):
        return self.send({"req": "play", "ids": list(ids), "index": index,
                          "start": start})

    def enqueue(self, ids, next_=False):
        return self.send({"req": "enqueue", "ids": list(ids), "next": next_})

    def remove_from_queue(self, index):
        return self.send({"req": "removeFromQueue", "index": index})

    def move_in_queue(self, from_, to):
        return self.send({"req": "moveInQueue", "from": from_, "to": to})

    def clear_queue(self):
        return self.send({"req": "clearQueue"})

    def write(self, action, id_):
        return self.send({"req": "write", "action": action, "id": id_})

    def refresh(self):
        return self.send({"req": "refresh"})

    def sign_in(self):
        return self.send({"req": "signIn"})

    def sign_out(self):
        return self.send({"req": "signOut"})

    def quit(self):
        return self.send({"req": "quit"})

    def close(self):
        if self._reader is not None:
            self._reader.stop()
            self._reader.wait(2000)
            self._reader = None
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.close()
                except OSError:
                    pass
                self._stream = None
