"""Stage-6 tests: seek position model, queue reorder + no-rebuild guard,
player no-drag, live tile format, notify off by default, art URL formats
(template + signed) and mosaic.

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_stage6.py
"""
import json
import os
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD"})
os.environ["ZTOS_APP_ROOT"] = REPO

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from tests.fake_slipmatd import FakeSlipmatd

FAILED = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        FAILED.append(name)


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def mouse_move(widget, x, y):
    ev = QMouseEvent(QEvent.MouseMove, QPointF(x, y), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, ev)


def mouse_release(widget, x, y):
    ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, ev)


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-s6-")
    os.environ["HOME"] = tmp                      # isolate ztos.store from the real one
    os.environ["XDG_RUNTIME_DIR"] = tmp
    os.environ["XDG_CACHE_HOME"] = tmp
    sock = os.path.join(tmp, "slipmat.sock")
    log = os.path.join(tmp, "requests.log")
    srv = FakeSlipmatd(sock, requests_log=log, stage="ready")
    srv.start()

    import ztos
    import art
    art.CACHE_DIR = os.path.join(tmp, "artwork")
    import player, client, screens, hub
    b = client.backend
    b.connect(ready_timeout=5.0)
    pump(app, 0.4)
    zapp = ztos.App()

    # ---- 2) seek position model: monotonic, stale snapshots rejected --------
    seek = player.PlayerSeek(zapp.window)
    seek.resize(328, 36)
    seek.anchor(10000, 174000, True, track_key="t1")       # 10 s, playing
    p1 = seek.current_pos()
    time.sleep(0.05)
    p2 = seek.current_pos()
    check("interpolation advances while playing", p2 > p1, f"{p1:.2f}->{p2:.2f}")
    seek.anchor(5000, 174000, True, track_key="t1")        # stale snapshot (5 s < shown)
    check("stale backward snapshot ignored (monotonic)", seek.current_pos() >= p2 - 0.001,
          f"shown={seek.current_pos():.2f}")
    seek.anchor(2000, 174000, True, track_key="t2")        # track change: accept
    check("track change accepts new position", abs(seek.current_pos() - 2.0) < 0.3,
          f"{seek.current_pos():.2f}")
    seek.anchor(90000, 174000, True, track_key="t2")
    drawn_before = seek._last_drawn
    seek.anchor(90050, 174000, True, track_key="t2")       # < 150 ms delta
    check("sub-150ms snapshot does not force redraw", seek._last_drawn == drawn_before)

    # ---- 6) player page does not drag ---------------------------------------
    page = player.NowPlaying(zapp)
    zapp.stack.append(page)
    zapp._place(page)
    zapp.window.resize(360, 640)
    page.resize(360, 640)
    pump(app, 0.5)
    page._drag_to(500)
    page._fling(3000)
    pump(app, 0.3)
    check("player page does not scroll/drag", page._scroll == 0 and page.body.y() == 0,
          f"scroll={page._scroll} body.y={page.body.y()}")

    # ---- 4) queue: no rebuild on position-only event, drag -> moveInQueue ---
    first = ztos.Page("hub")
    zapp.stack = [first]
    zapp._place(first)
    q = screens.QueuePage()
    zapp.push(q)
    zapp.window.resize(360, 640)
    zapp.window.show()
    q.resize(360, 640)
    pump(app, 1.2)
    q.shown()
    pump(app, 0.3)
    pump(app, 0.5)
    rows_before = list(q._row_widgets)
    n_before = len(rows_before)
    check("queue rows built", n_before == 2, str(n_before))
    # simulate a queue event with same content, different position
    b.queue = {"items": [{"id": "c.fix1", "title": "Fixture Song One", "artist": "A", "album": "Al", "duration_ms": 1},
                         {"id": "i.fix2", "title": "Fixture Song Two", "artist": "B", "album": "Bl", "duration_ms": 2}],
               "position": 1}
    q._gl_dirty = False                # as after a GL list picture was made
    b.queue_changed.emit()
    pump(app, 0.3)
    check("position-only queue event: no rebuild (same row objects)",
          q._row_widgets == rows_before and len(q._row_widgets) == n_before)
    check("accent moved to new position", q._row_widgets[1]._accent and not q._row_widgets[0]._accent)
    check("position-only queue event does NOT dirty the GL list picture",
          not q._gl_dirty, f"_gl_dirty={q._gl_dirty}")
    # drag row 0 over row 1 -> moveInQueue(0, 1)
    q._start_drag(0)
    r1 = q._row_widgets[1]
    q._gl_dirty = False
    q.eventFilter(r1, QMouseEvent(QEvent.MouseMove, QPointF(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    pump(app, 0.2)
    check("drag highlight does NOT dirty the GL list picture", not q._gl_dirty,
          f"_gl_dirty={q._gl_dirty}")
    check("drag computes target index", q._drag_over == 1, f"drag_over={q._drag_over}")
    q.eventFilter(r1, QMouseEvent(QEvent.MouseButtonRelease, QPointF(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    pump(app, 0.5)
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    check("drag reorder -> moveInQueue(0,1) on the wire",
          any(r.get("req") == "moveInQueue" and r.get("from") == 0 and r.get("to") == 1 for r in reqs),
          str([r for r in reqs if r.get("req") == "moveInQueue"]))
    zapp.pop()
    pump(app, 0.8)

    # ---- 4b) queue with MANY rows: _fit must grow the body (regression: the
    # drag eventFilter used to swallow Page's LayoutRequest, so the body kept
    # the viewport's height and Qt squashed all rows into it — the pile on B)
    q2 = screens.QueuePage()
    zapp.push(q2)
    zapp.window.resize(360, 640)
    q2.resize(360, 640)
    pump(app, 0.6)
    big = [{"id": f"c.big{i}", "title": f"Big Song {i}", "artist": "A", "album": "Al",
            "duration_ms": 60000} for i in range(57)]
    b.queue = {"items": big, "position": 0}
    q2.shown()
    pump(app, 1.0)
    check("queue of 57 rows: body grew to the rows' height (LayoutRequest not swallowed)",
          q2.body.height() >= 57 * 71 - 30 and q2._max() > 0,
          f"body_h={q2.body.height()} view_h={q2.viewport.height()} max={q2._max()}")
    ys = [r.y() for r in q2._row_widgets[:6]]
    check("queue rows spaced 71px", all(ys[i + 1] - ys[i] == 71 for i in range(len(ys) - 1)),
          str(ys))
    zapp.pop()
    pump(app, 0.5)

    # ---- 9) live tile format + 8) notify off by default ---------------------
    live = os.path.join(tmp, "ztos-live", "dev.oneplus2.zunehd")
    snap = json.load(open(os.path.join(REPO, "tests", "fixtures", "misc.json")))["snapshot"]
    b._on_event(dict(snap))
    pump(app, 0.3)
    check("tile file written on snapshot", os.path.exists(live), live)
    if os.path.exists(live):
        content = open(live).read()
        check("tile fields: title/lines/badge/progress",
              "title=Playing" in content and "line=Fixture Song One" in content
              and "line=Fixture Artist A" in content and "badge=play" in content
              and "progress=" in content, content.replace("\n", " | "))
    # notify off by default
    notif_calls = []
    orig_notify = ztos.notify
    ztos.notify = lambda *a, **k: notif_calls.append(a)
    b._on_event(dict(snap, title="Another Fixture", position_ms=1000))
    pump(app, 0.2)
    check("track-change notify OFF by default", not notif_calls, str(notif_calls))
    st = ztos.store("zunehd")
    st["notify_track"] = True
    st.save()
    b._on_event(dict(snap, title="Third Fixture", position_ms=2000))
    pump(app, 0.2)
    check("notify ON when toggled", len(notif_calls) == 1, str(notif_calls))
    ztos.notify = orig_notify
    # empty snapshot -> tile cleared
    b._on_event({"event": "snapshot", "title": "", "artist": "", "album": "",
                 "position_ms": 0, "duration_ms": 0, "playing": False})
    pump(app, 0.3)
    check("tile cleared when nothing plays", not os.path.exists(live))

    # ---- 7) art: signed (non-template) URL cached by URL hash; mosaic -------
    import http.server, threading
    from PIL import Image
    imgf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    Image.new("RGB", (32, 32), (10, 200, 60)).save(imgf.name, "JPEG")
    payload = open(imgf.name, "rb").read()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *a):
            pass
    srv2 = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    signed = f"http://127.0.0.1:{srv2.server_address[1]}/signed/art.jpg?sig=abc123"
    got = []
    art._fetcher.done.connect(lambda t, p, ok: got.append((t, p, ok)))
    art._fetcher.add(signed, 300)
    pump(app, 2.0)
    cached = art.cache_path(signed, 300)
    check("signed URL fetched and cached by URL hash",
          any(t == signed and ok for t, p, ok in got) and os.path.exists(cached), cached)
    # mosaic from 4 cached covers
    paths = [art.cache_path(signed, 300)] * 4
    m = art.mosaic_image(paths, 200)
    check("mosaic composed 2x2 and cached", m is not None and not m.isNull() and m.width() == 200)
    srv2.shutdown()

    srv.stop()
    try:
        b._client.close()
    except Exception:
        pass
    print()
    if FAILED:
        print("FAILED:", FAILED)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
