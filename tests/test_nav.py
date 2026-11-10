"""Navigation smoke test with the REAL SDK code: builds the music hub and
exercises every navigation (push player/detail/queue/search/settings, pivot
turns, song-row play, options menu, sort menu), capturing sys.excepthook,
direct exceptions and Qt messages. FAILS if any exception is raised during
navigation — this is the regression test for the 'list object is not callable'
bug (SongsPage._rows shadowing Page._rows(), seen in the B log at hub.py:315
-> push -> _row_bands -> Pivot._rows -> Page._rows).

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_nav.py
"""
import json
import os
import sys
import tempfile
import time
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD",
                                          "caps": "ZUNE HD", "version": "0.1.0"})
os.environ["ZTOS_APP_ROOT"] = REPO

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from tests.fake_slipmatd import FakeSlipmatd

ERRORS = []


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-nav-")
    os.environ["XDG_RUNTIME_DIR"] = tmp
    srv = FakeSlipmatd(os.path.join(tmp, "slipmat.sock"), stage="ready")
    srv.start()

    sys.excepthook = lambda t, v, tb: ERRORS.append("".join(traceback.format_exception(t, v, tb)))

    def qt_msg(mode, ctx, msg):
        if "TypeError" in msg or "AttributeError" in msg or "Traceback" in msg:
            ERRORS.append(msg)
    qInstallMessageHandler(qt_msg)

    import ztos
    import hub, player, screens, client
    client.backend.connect(ready_timeout=5.0)
    pump(app, 0.4)

    zapp = ztos.App()
    music = hub.MusicHub(zapp)
    zapp.stack.append(music)
    zapp._place(music)
    zapp.window.resize(360, 640)
    music.resize(360, 640)
    pump(app, 1.2)

    def nav(name, fn):
        try:
            fn()
        except Exception:
            ERRORS.append(f"{name}: " + traceback.format_exc())
        pump(app, 1.2)

    # the _rows collision fires when the CURRENT pivot page is SongsPage
    # (push -> _row_bands -> Pivot._rows -> current()._rows()): go there first
    songs_page = next(p for p in music._pages if isinstance(p, hub.SongsPage))
    songs_idx = music._pages.index(songs_page)
    nav("pivot turn songs", lambda: music.turn(songs_idx))
    # every push from the hub (pivot) page — this is where _row_bands runs
    nav("push now playing", lambda: zapp.push(player.NowPlaying(zapp)))
    nav("pop", lambda: zapp.pop())
    nav("push queue", lambda: zapp.push(screens.QueuePage()))
    nav("pop", lambda: zapp.pop())
    nav("push search", lambda: zapp.push(screens.SearchPage()))
    nav("pop", lambda: zapp.pop())
    nav("push detail album", lambda: zapp.push(hub.DetailPage("libraryAlbum", "al.fix1")))
    nav("pop", lambda: zapp.pop())
    # pivot turns (settings is index 4)
    for i in range(5):
        nav(f"pivot turn {i}", lambda i=i: music.turn(i))
    # song row play (SongsPage._play -> play_list -> push player)
    nav("songs fill", lambda: songs_page.fill())
    nav("play song row 0", lambda: songs_page._play(0))
    nav("pop player", lambda: zapp.pop())
    # options menu + sort menu from the player / hub
    nav("open options", lambda: zapp.push(player.NowPlaying(zapp)) or pump(app, 0.5) or zapp.page._open_options())
    nav("pop", lambda: zapp.pop())
    nav("sort menu", lambda: music._sort_menu())

    pump(app, 1.0)
    srv.stop()
    try:
        client.backend._client.close()
    except Exception:
        pass

    print()
    if ERRORS:
        print(f"FAIL: {len(ERRORS)} exception(s) during navigation:")
        for e in ERRORS[:4]:
            print("---", e[:600])
        return 1
    print("ALL PASS: no exceptions during any navigation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
