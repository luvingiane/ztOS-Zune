"""Zune HD perf instrumentation — ON with ZUNE_PERF=1, OFF otherwise.

Measures from OUTSIDE the SDK (monkeypatching the runtime classes at import
time): no file of the SDK is modified, so the app binary runs the SDK exactly
as the phone's own apps do. What is measured, once per second, printed to
stderr (on the phone the SDK bootstrap redirects stderr to
~/.local/state/ztos/<id>.log):

  frames        _Surface.paintGL calls (layer frames submitted)
  swaps         _Surface.frameSwapped (frames actually presented, vsync-paced)
  d_paint       ms between two consecutive paintGL calls: avg/min/max
  d_swap        ms between two consecutive frameSwapped: avg/min/max
                (this is the real frame-to-frame time, not the render time)
  draw          CPU ms inside the native zsdk_draw call: avg/max, quads avg/max
  identical     paintGL frames whose quad list is equal to the previous frame's
                (updates drawn with no content change)
  uploads       textures uploaded to the GPU: count, total bytes, biggest (w*h)
  raster        CPU ms of Qt's raster passes: _snapshot / Page._gl_prepare /
                Page._print / _Pressable.paintEvent / _Moving.paintEvent
  refreshes     Layer.refresh() calls (update requests to the layer)
  paints        QEvent.Paint delivered to widgets (via _Finger's filter)
  changes       Page._changed() calls (content actually changed)

Each metric is a per-second window, one line: "zune-perf ...".
"""
import os
import time

_ENABLED = bool(os.environ.get("ZUNE_PERF"))

if _ENABLED:
    import ztos
    from PySide6.QtCore import QEvent, QTimer
    from PySide6.QtWidgets import QWidget

    _t0 = time.perf_counter()

    def _now():
        return time.perf_counter()

    class _Win:
        """One second of measurements."""

        def __init__(self):
            self.frames = 0            # paintGL calls
            self.swaps = 0             # frameSwapped
            self.refreshes = 0         # Layer.refresh
            self.uploads = 0
            self.upload_bytes = 0
            self.upload_max = 0        # biggest w*h
            self.draw_ms = 0.0
            self.draw_max = 0.0
            self.quads = 0
            self.quads_max = 0
            self.identical = 0
            self.paints = 0            # QEvent.Paint on widgets
            self.changes = 0           # Page._changed
            self.raster = {}           # label -> [count, ms_total, ms_max]
            self.last_paint = None     # perf_counter of the last paintGL
            self.last_swap = None
            self.d_paint = []          # intervals this window
            self.d_swap = []

        def raster_add(self, label, ms):
            e = self.raster.setdefault(label, [0, 0.0, 0.0])
            e[0] += 1
            e[1] += ms
            e[2] = max(e[2], ms)

    _win = _Win()
    _prev_sig = None
    _live_tex = {}      # (id(layer), key) -> bytes, for the "texture vive/byte" report

    def _stats(v):
        if not v:
            return "0/0/0"
        return f"{sum(v) / len(v):.1f}/{min(v):.1f}/{max(v):.1f}"

    def _report():
        global _win, _prev_sig
        w = _win
        _win = _Win()
        _prev_sig = None
        raster = " ".join(f"{k}={v[0]}x{v[1]:.0f}ms(max{v[2]:.0f})"
                          for k, v in sorted(w.raster.items()))
        tex_n = len(_live_tex)
        tex_b = sum(_live_tex.values())
        line = (f"zune-perf t={_now() - _t0:7.1f}s frames={w.frames} swaps={w.swaps} "
                f"refreshes={w.refreshes} "
                f"d_paint(avg/min/max)={_stats(w.d_paint)} d_swap={_stats(w.d_swap)} "
                f"draw_ms(avg/max)={w.draw_ms / max(1, w.frames):.2f}/{w.draw_max:.2f} "
                f"quads(avg/max)={w.quads / max(1, w.frames):.1f}/{w.quads_max} identical={w.identical} "
                f"uploads={w.uploads} bytes={w.upload_bytes} maxpx={w.upload_max} "
                f"tex_live={tex_n} tex_live_bytes={tex_b} "
                f"raster[{raster}] paints={w.paints} changes={w.changes}")
        print(line, file=__import__("sys").stderr, flush=True)

    def _wrap(owner, name, fn):
        original = getattr(owner, name)

        def wrapped(*args, **kwargs):
            return fn(original, *args, **kwargs)

        setattr(owner, name, wrapped)

    def _timed_raster(owner, name, label):
        def fn(original, *args, **kwargs):
            t = _now()
            try:
                return original(*args, **kwargs)
            finally:
                _win.raster_add(label, (_now() - t) * 1000.0)
        _wrap(owner, name, fn)

    def install(app):
        """Hook the SDK's per-frame points. Called once from main.py, after the
        App exists (for the timer); everything is a no-op when ZUNE_PERF is off."""
        if not _ENABLED:
            return
        from ztos import _gl as glmod
        from ztos import _native

        # --- the native renderer: quads per frame, CPU time, texture uploads ---
        def draw(original, self, quads, textures, w, h, dpr):
            global _prev_sig
            t = _now()
            try:
                return original(self, quads, textures, w, h, dpr)
            finally:
                ms = (_now() - t) * 1000.0
                _win.draw_ms += ms
                _win.draw_max = max(_win.draw_max, ms)
                _win.quads += len(quads)
                _win.quads_max = max(_win.quads_max, len(quads))
                sig = tuple((q.key, round(q.src.left(), 3), round(q.src.top(), 3),
                             round(q.src.width(), 3), round(q.src.height(), 3),
                             tuple(round(c, 1) for pt in q.corners for c in pt),
                             round(q.alpha, 3)) for q in quads)
                if sig == _prev_sig and sig:
                    _win.identical += 1
                _prev_sig = sig
        _wrap(_native.Renderer, "draw", draw)

        def upload(original, self, image):
            t = _now()
            try:
                return original(self, image)
            finally:
                _win.uploads += 1
                _win.upload_bytes += image.width() * image.height() * 4
                _win.upload_max = max(_win.upload_max, image.width() * image.height())
                _win.raster_add("upload", (_now() - t) * 1000.0)
        _wrap(_native.Renderer, "upload", upload)

        # --- the GL surface: paintGL count/pacing, frameSwapped (presented) ---
        def paint_gl(original, self):
            t = _now()
            try:
                return original(self)
            finally:
                _win.frames += 1
                if _win.last_paint is not None:
                    _win.d_paint.append((t - _win.last_paint) * 1000.0)
                _win.last_paint = t
        _wrap(glmod._Surface, "paintGL", paint_gl)

        def next_frame(original, self):
            t = _now()
            try:
                return original(self)
            finally:
                _win.swaps += 1
                if _win.last_swap is not None:
                    _win.d_swap.append((t - _win.last_swap) * 1000.0)
                _win.last_swap = t
        _wrap(glmod._Surface, "_next", next_frame)

        def refresh(original, self):
            _win.refreshes += 1
            return original(self)
        _wrap(glmod.Layer, "refresh", refresh)

        # live textures on the GPU layer: uploads minus drops, with bytes
        def layer_upload(original, self, key, image):
            try:
                return original(self, key, image)
            finally:
                _live_tex[(id(self), key)] = image.width() * image.height() * 4
        _wrap(glmod.Layer, "upload", layer_upload)

        def layer_drop(original, self, key):
            try:
                return original(self, key)
            finally:
                _live_tex.pop((id(self), key), None)
        _wrap(glmod.Layer, "drop", layer_drop)

        # --- Qt's raster passes (CPU): snapshots, list prints, row paints ---
        plain_snapshot = ztos._snapshot

        def snapshot(widget, size=None, **kwargs):
            t = _now()
            try:
                return plain_snapshot(widget, size, **kwargs)
            finally:
                _win.raster_add("snapshot", (_now() - t) * 1000.0)
        ztos._snapshot = snapshot
        _timed_raster(ztos.Page, "_gl_prepare", "gl_prepare")
        _timed_raster(ztos.Page, "_print", "print")
        _timed_raster(ztos.Page, "_verify", "verify")
        _timed_raster(ztos._Pressable, "paintEvent", "pressable_paint")
        _timed_raster(ztos._Moving, "paintEvent", "moving_paint")

        def changed(original, self, *args, **kwargs):
            _win.changes += 1
            return original(self, *args, **kwargs)
        _wrap(ztos.Page, "_changed", changed)

        # --- widget repaints, seen where every event already goes past ---
        def event_filter(original, self, obj, event):
            if event.type() == QEvent.Paint and isinstance(obj, QWidget):
                _win.paints += 1
            return original(self, obj, event)
        _wrap(ztos._Finger, "eventFilter", event_filter)

        timer = QTimer(app.qt, interval=1000)
        timer.timeout.connect(_report)
        timer.start()
        print(f"zune-perf: ON (pid {os.getpid()})", file=__import__("sys").stderr, flush=True)
else:
    def install(app):
        return
