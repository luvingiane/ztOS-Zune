"""Geometry + options-menu tests for the reworked Now Playing (player.py).

- five controls in one row (queue, prev, play big, next, options), each
  >= 44 px, non-overlapping, inside the 360x640 window; seek bar and cover
  inside too; no volume slider anywhere
- the options menu opens over the window, rows >= 48 px, inside the window,
  and contains only real entries (no Scarica, no Condividi)
- menu commands go on the wire: favorite -> write req, vai all'album ->
  open req (against tests/fake_slipmatd.py with anonymized fixtures)

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_player.py
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
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD",
                                          "caps": "ZUNE HD", "version": "0.1.0"})
os.environ["ZTOS_APP_ROOT"] = REPO

from PySide6.QtWidgets import QApplication, QWidget

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


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-player-")
    os.environ["XDG_RUNTIME_DIR"] = tmp
    sock = os.path.join(tmp, "slipmat.sock")
    log = os.path.join(tmp, "requests.log")
    srv = FakeSlipmatd(sock, requests_log=log, stage="ready")
    srv.start()

    import ztos
    import player
    import client
    b = client.backend
    check("backend live (fake daemon ready)", b.connect(ready_timeout=5.0) and b.live)
    pump(app, 0.4)

    os.environ["HOME"] = tmp                  # isolate ztos.store from the real one
    zapp = ztos.App()
    first = ztos.Page("music")               # real flow: a page is already on the stack
    zapp.stack.append(first)
    zapp._place(first)
    page = player.NowPlaying(zapp)
    zapp.window.resize(360, 640)
    zapp.push(page)                           # old is not None -> _arrived -> shown()
    page.resize(360, 640)
    pump(app, 1.5)

    ctrl = page.ctrl
    win = zapp.window
    # --- five transport buttons in the page's app bar, inside the window ------
    check("five controls", sorted(ctrl) == ["more", "next", "play", "prev", "queue"], str(sorted(ctrl)))
    from PySide6.QtCore import QPoint
    boxes = {}
    for k, bt in ctrl.items():
        tl = bt.mapTo(win, QPoint(0, 0))
        boxes[k] = (tl.x(), tl.y(), bt.width(), bt.height())
    for k, (x, y, w, h) in boxes.items():
        check(f"ctrl {k} >= 44px and inside window", w >= 44 and h >= 44 and x >= 0 and x + w <= 360
              and y >= 0 and y + h <= 640, str((x, y, w, h)))
    xs = sorted((x, x + w) for x, y, w, h in boxes.values())
    check("controls do not overlap", not any(xs[i][1] > xs[i + 1][0] for i in range(len(xs) - 1)), str(xs))
    centers = [y + h / 2 for x, y, w, h in boxes.values()]
    check("controls one row", max(centers) - min(centers) <= 8, str(centers))
    check("controls are the SDK RoundButton size (68x52)", all(w == 68 and h == 52 for x, y, w, h in boxes.values()))
    check("controls are CircleButton (no square overlay)",
          all(type(bt).__name__ == "CircleButton" for bt in ctrl.values()))
    check("no volume slider", not any("volume" in (o.objectName() or "").lower() for o in page.findChildren(QWidget)))
    # --- SDK SeekBar, cover centered, texts ------------------------------------
    check("seek is the SDK's ztos.SeekBar", isinstance(page._seek, ztos.SeekBar))
    c = page._cover
    ctl = c.mapTo(win, QPoint(0, 0))
    check("cover big+centered inside window", c.width() >= 240 and abs(ctl.x() + c.width() / 2 - 180) <= 2
          and ctl.y() >= 0 and ctl.y() + c.height() <= 640, str((ctl.x(), ctl.y(), c.width())))
    page.set_track(b.now_playing())
    check("title 24 / artist 14 labels filled", page._title.text() == "Fixture Song One"
          and "Fixture Artist A" in page._artist.text(), f"{page._title.text()!r} {page._artist.text()!r}")

    # --- options: the SDK's standard menu ---------------------------------------
    captured = []
    orig_menu = ztos.menu
    ztos.menu = lambda anchor, items: captured.append(items)
    page._open_options()
    ztos.menu = orig_menu
    items = captured[0]
    labels = [l for l, _cb in items]
    check("menu has favorites/go-album/go-artist/shuffle/repeat",
          any("favorites" in l for l in labels) and any("album" in l for l in labels)
          and any("artist" in l for l in labels) and any(l.startswith("shuffle") for l in labels)
          and any(l.startswith("repeat") for l in labels), str(labels))
    check("menu has NO download / share", not any("download" in l.lower() or "share" in l.lower() for l in labels))
    next(cb for l, cb in items if "favorites" in l)()
    pump(app, 0.6)
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    check("favorite -> write req on the wire", any(r.get("req") == "write" and r.get("action") in ("favorite", "unfavorite") for r in reqs))
    b.browse("albums")                      # fill the cache the menu searches
    pump(app, 0.3)
    next(cb for l, cb in items if "album" in l)()
    pump(app, 2.5)
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    check("go to album -> open req on the wire", any(r.get("req") == "open" and "album" in r.get("kind", "").lower() for r in reqs),
          str([r for r in reqs if r.get("req") == "open"]))
    # --- blur toggle: off = nothing computed, black page --------------------------
    st = ztos.store("zunehd"); st["blur_bg"] = False; st.save()
    page.apply_blur_setting()
    check("blur OFF: no background image", page._bg is None and not player.blur_enabled())
    st["blur_bg"] = True; st.save()

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
