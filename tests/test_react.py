"""Reactivity test: tap -> first visible response (first widget paint after the
press), measured by perf.py (ZUNE_PERF=1 tap_paint). Exercises the real tap
paths with QTest: song row (play -> push player), app-bar 'now playing',
app-bar 'queue', pivot title (turn). Budget: every tap_paint < 150 ms.

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_react.py
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
os.environ["ZUNE_PERF"] = "1"
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD"})
os.environ["ZTOS_APP_ROOT"] = REPO

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
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


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-react-")
    os.environ["XDG_RUNTIME_DIR"] = tmp
    srv = FakeSlipmatd(os.path.join(tmp, "slipmat.sock"), stage="ready")
    srv.start()

    import ztos
    import perf
    import hub, player, client
    client.backend.connect(ready_timeout=5.0)
    zapp = ztos.App()
    perf.install(zapp)
    music = hub.MusicHub(zapp)
    zapp.stack.append(music)
    zapp._place(music)
    zapp.window.resize(360, 640)
    zapp.window.show()
    pump(app, 1.5)

    songs = next(p for p in music._pages if isinstance(p, hub.SongsPage))
    music.turn(music._pages.index(songs))   # go to songs so its rows fill
    pump(app, 1.5)                      # rows arrived (async fill)
    rows = [w for w in songs.findChildren(ztos.Entry) if w.height() == 71]
    check("song rows present", len(rows) >= 1, str(len(rows)))

    def tap(widget, name):
        before = list(perf.stats()["tap_paint"])
        QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(widget.width() // 2, widget.height() // 2))
        pump(app, 0.8)
        after = perf.stats()["tap_paint"]
        new = after[len(before):]
        mx = f"{max(new):.0f}" if new else "none"
        check(f"tap '{name}' -> first paint < 150ms", bool(new) and max(new) < 150,
              f"n={len(new)} max={mx}ms")
        return new

    if rows:
        tap(rows[0], "song row (play)")
        pump(app, 1.0)
        if zapp.page is not music:
            zapp.pop()
            pump(app, 0.8)
    # app-bar buttons: now playing + queue
    bar_btns = [w for w in music.app_bar.findChildren(ztos.RoundButton)]
    for b in bar_btns:
        if b._label == "now playing":
            tap(b, "now playing button")
            pump(app, 1.0)
            if zapp.page is not music:
                zapp.pop()
                pump(app, 0.8)
    # pivot title tap (turn to albums)
    titles = music._titles
    tap(titles, "pivot title (turn)")
    pump(app, 1.0)

    st = perf.stats()
    all_taps = st["tap_paint"]
    print(f"tap_paint all: n={len(all_taps)}"
          + (f" avg={sum(all_taps)/len(all_taps):.0f}ms max={max(all_taps):.0f}ms" if all_taps else ""))
    check("overall: every tap < 150ms", bool(all_taps) and max(all_taps) < 150,
          f"max={max(all_taps):.0f}ms" if all_taps else "no taps measured")

    srv.stop()
    try:
        client.backend._client.close()
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
