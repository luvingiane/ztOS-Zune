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

    zapp = ztos.App()
    first = ztos.Page("music")               # real flow: a page is already on the stack
    zapp.stack.append(first)
    zapp._place(first)
    page = player.NowPlaying(zapp)
    zapp.window.resize(360, 640)
    zapp.push(page)                           # old is not None -> _arrived -> shown()
    page.resize(360, 640)
    pump(app, 1.5)

    view = page.view
    ctrl = view.ctrl
    # usable area = window minus shell chrome (ztmetro.c:128-131: status 28, nav 40)
    UX0, UY0, UW, UH = 0, player.TOP_INSET, 360, 640 - player.TOP_INSET - player.BOTTOM_INSET
    # --- five controls in one row, inside the USABLE area --------------------
    check("five controls", sorted(ctrl) == ["more", "next", "play", "prev", "queue"],
          str(sorted(ctrl)))
    boxes = {k: (b.x(), b.y(), b.width(), b.height()) for k, b in ctrl.items()}
    for k, (x, y, w, h) in boxes.items():
        inside = w >= 44 and h >= 44 and x >= UX0 and x + w <= UX0 + UW and y >= UY0 and y + h <= UY0 + UH
        check(f"ctrl {k} >= 44px and inside usable area", inside, str((x, y, w, h)))
    xs = sorted((x, x + w) for x, y, w, h in boxes.values())
    overlap = any(xs[i][1] > xs[i + 1][0] for i in range(len(xs) - 1))
    check("controls do not overlap", not overlap, str(xs))
    centers = {k: y + h / 2 for k, (x, y, w, h) in boxes.items()}
    check("controls one row (centers aligned within 8px)",
          max(centers.values()) - min(centers.values()) <= 8, str(centers))
    check("controls are the SDK standard RoundButton size (68x52)",
          all(w == 68 and h == 52 for x, y, w, h in boxes.values()), str(boxes))
    # no volume slider
    check("no volume slider", not any("volume" in (o.objectName() or "").lower()
                                      for o in page.findChildren(QWidget))
          and not hasattr(page, "_vol"))
    # seek + big centered cover inside the usable area
    s = view._seek
    check("seek inside usable area", s.x() >= UX0 and s.x() + s.width() <= UX0 + UW
          and s.y() >= UY0 and s.y() + s.height() <= UY0 + UH,
          str((s.x(), s.y(), s.width(), s.height())))
    c = view._cover
    check("cover big+centered, inside usable area",
          c.width() >= 280 and abs((c.x() + c.width() / 2) - UW / 2) <= 2
          and c.x() >= UX0 and c.y() >= UY0 and c.y() + c.height() <= UY0 + UH,
          str((c.x(), c.y(), c.width(), c.height())))

    # --- options menu ---------------------------------------------------------
    track = b.now_playing()
    menu = player.OptionsMenu(zapp.window, track)
    menu.show()
    pump(app, 0.3)
    check("menu inside window", 0 <= menu.x() and menu.x() + menu.width() <= 360
          and 0 <= menu.y() and menu.y() + menu.height() <= 640,
          str((menu.x(), menu.y(), menu.width(), menu.height())))
    labels = [it[1] for it in menu._items]
    check("menu has favorites/go-album/go-artist/shuffle/repeat",
          any("preferiti" in l for l in labels) and any("album" in l for l in labels)
          and any("artista" in l for l in labels) and "shuffle" in labels and "repeat" in labels,
          str(labels))
    check("menu has NO Scarica and NO Condividi", not any("carica" in l.lower() or "condividi" in l.lower() for l in labels),
          str(labels))
    check("menu rows >= 48px", player.OptionsMenu.ROW_H >= 48 and len(menu._items) * player.OptionsMenu.ROW_H + 20 <= menu.height() + 1)
    # favorite command goes on the wire
    fav_item = next(it for it in menu._items if "preferiti" in it[1])
    fav_item[3]()
    pump(app, 0.6)
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    check("favorite -> write req on the wire", any(r.get("req") == "write" and r.get("action") in ("favorite", "unfavorite") for r in reqs))
    # vai all'album -> browse albums (cached) then open
    go_album = next(it for it in menu._items if "album" in it[1])
    b.browse("albums")                      # fill the cache the menu searches
    pump(app, 0.3)
    go_album[3]()
    pump(app, 2.5)                          # push turnstile + shown() -> open req
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    check("vai all'album -> open req on the wire", any(r.get("req") == "open" and "album" in r.get("kind", "").lower() for r in reqs),
          str([r for r in reqs if r.get("req") == "open"]))

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
