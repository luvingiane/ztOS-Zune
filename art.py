"""Artwork: template -> concrete URL -> disk cache -> async load -> widget.

Mirrors slipmat-core's artwork.rs: cache key is FNV-1a of the template
(music/types.rs:116-126), file name `<fnv>-<size>.jpg` under
`~/.cache/zunehd/artwork/` — the same naming the daemon uses for its own
cache (`~/.cache/slipmat/artwork/…`), so a snapshot `art_path` shows at once.

Network happens only off the GUI thread (one worker per batch), and only at
sizes matched to what is on screen (grid 300, now playing 512) — never a
full-screen image: the phone would decode pixels it never shows, and every
decoded byte lands in the page snapshot the SDK uploads as a texture.
"""
import os
import threading
import urllib.request

import ztos
from PySide6.QtCore import QObject, QRectF, QThread, Signal
from PySide6.QtGui import QImage, QPainter

from slipmat.ipc import art_url

CACHE_DIR = os.path.expanduser("~/.cache/zunehd/artwork")


def _fnv1a(text: str) -> str:
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def cache_path(template: str, size: int) -> str:
    return os.path.join(CACHE_DIR, f"{_fnv1a(template)}-{size}.jpg")


def local_art(path_or_template, size: int = 512):
    """A local file for this artwork if we already have it (no network)."""
    if not path_or_template:
        return None
    if os.path.isabs(str(path_or_template)) and os.path.exists(path_or_template):
        return str(path_or_template)                  # snapshot's art_path
    if "{w}" in str(path_or_template):
        p = cache_path(str(path_or_template), size)
        return p if os.path.exists(p) else None
    return None


class _Fetcher(QObject):
    """Downloads queued (template, size) pairs on a worker thread."""
    done = Signal(str, str, bool)      # template, local path, ok

    def __init__(self):
        super().__init__()
        self._queue = []
        self._lock = threading.Lock()
        self._busy = False

    def add(self, template, size):
        if not template or "{w}" not in str(template):
            return
        p = cache_path(str(template), size)
        if os.path.exists(p):
            self.done.emit(str(template), p, True)
            return
        with self._lock:
            if (template, size) not in self._queue:
                self._queue.append((template, size))
            start = not self._busy
            self._busy = True
        if start:
            QThread.create(self._run)

    def _run(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._busy = False
                    return
                template, size = self._queue.pop(0)
            url = art_url(template, size)
            path = cache_path(template, size)
            ok = False
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                tmp = path + ".part"
                with urllib.request.urlopen(url, timeout=10) as r, open(tmp, "wb") as f:
                    f.write(r.read())
                os.replace(tmp, path)
                ok = True
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            self.done.emit(template, path if ok else "", ok)


_fetcher = _Fetcher()
_images = {}          # local path -> QImage (decoded once, shared, small cap)


def image_for(path: str):
    img = _images.get(path)
    if img is None and path and os.path.exists(path):
        img = QImage(path)
        if not img.isNull():
            if len(_images) > 64:
                _images.pop(next(iter(_images)))
            _images[path] = img
    return img


def prewarm(items, size: int):
    """Queue the artwork of these entry-dicts for download, so covers are on
    disk before the page is shown or turned to."""
    for d in items:
        t = d.get("artworkTemplate") or ""
        if t:
            _fetcher.add(t, size)


class Artwork(ztos.Entry):
    """A cover: gradient at once, real image swapped in when the fetch lands."""

    def __init__(self, size: int, title: str, template: str = "", art_size: int = 300):
        super().__init__("", "")
        self._cover_title = title
        self._template = ""
        self._art_size = art_size
        self._img = None
        self.setFixedSize(size, size)
        _fetcher.done.connect(self._on_done)
        if template:
            self.set_template(template, title)

    def set_template(self, template: str, title: str = ""):
        if title:
            self._cover_title = title
        self._template = template or ""
        p = local_art(self._template, self._art_size) if self._template else None
        self._img = image_for(p) if p else None
        if self._template and not self._img:
            _fetcher.add(self._template, self._art_size)
        self.redraw()
        self.content_changed()

    def _on_done(self, template, path, ok):
        if ok and template == self._template:
            img = image_for(path)
            if img is not None and img is not self._img:
                self._img = img
                self.redraw()
                self.content_changed()

    def draw(self, p: QPainter):
        rect = QRectF(0, 0, self.width(), self.height())
        if self._img is not None and not self._img.isNull():
            p.drawImage(rect, self._img)
        else:
            from widgets import draw_cover
            draw_cover(p, rect, self._cover_title)
