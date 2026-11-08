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
from PySide6.QtCore import QObject, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter

from slipmat.ipc import art_url

CACHE_DIR = os.path.expanduser("~/.cache/zunehd/artwork")


def _fnv1a(text: str) -> str:
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def cache_path(template: str, size: int) -> str:
    template = str(template)
    if "{w}" not in template:
        # signed/plain URL (no template, e.g. expiring playlist art): one cache
        # entry per URL itself
        return os.path.join(CACHE_DIR, f"{_fnv1a(template)}.jpg")
    return os.path.join(CACHE_DIR, f"{_fnv1a(template)}-{size}.jpg")


stale = set()     # URLs whose fetch failed (signed ones expire -> re-browse)


def local_art(path_or_template, size: int = 512):
    """A local file for this artwork if we already have it (no network).
    Handles both template URLs ({w}x{h}) and plain/signed URLs."""
    if not path_or_template:
        return None
    path_or_template = str(path_or_template)
    if os.path.isabs(path_or_template) and os.path.exists(path_or_template):
        return path_or_template                       # snapshot's art_path
    if path_or_template.startswith("http"):
        p = cache_path(path_or_template, size)
        return p if os.path.exists(p) else None
    return None


CACHE_MAX_BYTES = 24 * 1024 * 1024     # 24 MB cap for the on-disk art cache


def _evict_cache():
    """Keep the disk cache under CACHE_MAX_BYTES: evict oldest files first."""
    try:
        files = [(os.path.getmtime(os.path.join(CACHE_DIR, f)), os.path.join(CACHE_DIR, f))
                 for f in os.listdir(CACHE_DIR) if f.endswith(".jpg")]
    except OSError:
        return
    total = sum(os.path.getsize(p) for _, p in files)
    for _, p in sorted(files):
        if total <= CACHE_MAX_BYTES:
            return
        try:
            total -= os.path.getsize(p)
            os.unlink(p)
        except OSError:
            pass


class _FetchThread(QThread):
    """One worker thread; `done` is emitted from run() and delivered to the
    GUI thread as a queued signal (Qt signals only, never touch widgets from
    here). QThread.create() does NOT exist in PySide6 — that was the crash on
    the phone (art.py:73 AttributeError), this replaces it."""
    done = Signal(str, str, bool)      # template, local path, ok

    def __init__(self):
        super().__init__()
        self._queue = []
        self._lock = threading.Lock()

    def add(self, template, size):
        template = str(template)
        if not template or not template.startswith("http"):
            return
        p = cache_path(template, size)
        if os.path.exists(p):
            self.done.emit(template, p, True)
            return
        with self._lock:
            if (template, size) not in self._queue:
                self._queue.append((template, size))
        if not self.isRunning():
            self.start()

    def run(self):
        while True:
            with self._lock:
                if not self._queue:
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
                _evict_cache()
                ok = True
            except Exception as exc:
                stale.add(template)          # signed URLs expire: caller re-browses
                print(f"zunehd art: fetch failed for {url}: {exc}", flush=True)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            self.done.emit(template, path if ok else "", ok)


class _Fetcher(QObject):
    """Facade: queues downloads on the single _FetchThread and re-emits."""
    done = Signal(str, str, bool)

    def __init__(self):
        super().__init__()
        self._thread = _FetchThread()
        self._thread.done.connect(self.done)         # started lazily on first add

    def add(self, template, size):
        self._thread.add(template, size)


_fetcher = _Fetcher()
_listeners = {}       # template -> [cb(template, path, ok)]; ONE signal connection total


def _dispatch(template, path, ok):
    for cb in list(_listeners.get(template, [])):
        try:
            cb(template, path, ok)
        except Exception:
            pass


_fetcher.done.connect(_dispatch)


def add_listener(cb, template):
    """Register a listener for a template; fires immediately if already cached."""
    _listeners.setdefault(template, []).append(cb)
    p = local_art(template, 300)
    if p:
        cb(template, p, True)


_images = {}          # local path -> QImage (decoded once, shared, small cap)
_IMAGES_MAX_BYTES = 24 * 1024 * 1024
_images_bytes = 0
_thumbs = {}          # (path, px) -> QImage pre-scaled to display size, shared by all rows


def thumb_image(path: str, px: int):
    """The artwork pre-scaled ONCE to px x px (DPR included) and shared by
    every row showing it — paints then only copy a small pixmap."""
    key = (path, px)
    img = _thumbs.get(key)
    if img is None:
        src = image_for(path)
        if src is None or src.isNull():
            return None
        img = src.scaled(px, px, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if len(_thumbs) > 256:
            _thumbs.pop(next(iter(_thumbs)))
        _thumbs[key] = img
    return img


def image_for(path: str):
    global _images_bytes
    img = _images.get(path)
    if img is None and path and os.path.exists(path):
        img = QImage(path)
        if not img.isNull():
            size = img.width() * img.height() * 4
            while _images_bytes > _IMAGES_MAX_BYTES and _images:
                k = next(iter(_images))
                _images_bytes -= _images[k].width() * _images[k].height() * 4
                _images.pop(k)
            _images[path] = img
            _images_bytes += size
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
        if template:
            self.set_template(template, title)

    def set_template(self, template: str, title: str = ""):
        if title:
            self._cover_title = title
        self._template = template or ""
        p = local_art(self._template, self._art_size) if self._template else None
        self._img = image_for(p) if p else None
        if self._template:
            add_listener(self._on_done, self._template)
            if not self._img:
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


def mosaic_image(paths, size: int = 300):
    """2x2 mosaic of the first four cached covers (Apple playlists often have
    no artwork of their own — the original composes one, mosaic.rs:4-29)."""
    from PySide6.QtGui import QImage, QPainter
    imgs = [image_for(p) for p in paths[:4]]
    imgs = [i for i in imgs if i is not None and not i.isNull()]
    if not imgs:
        return None
    out = QImage(size, size, QImage.Format_RGB32)
    out.fill(QColor(38, 38, 38))
    p = QPainter(out)
    n = len(imgs)
    cell = size // 2
    for i, im in enumerate(imgs):
        x, y = (i % 2) * cell, (i // 2) * cell
        p.drawImage(QRectF(x, y, cell, cell), im)
    p.end()
    # disk cache named after the four source keys (mosaic.rs:23-29)
    key = "".join(_fnv1a(str(p_)) for p_ in paths[:4])
    mp = os.path.join(CACHE_DIR, f"mosaic-{key}.jpg")
    out.save(mp, "JPG")
    _images[mp] = out
    return out
