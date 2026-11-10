"""Detail pages (album, artist, library artist) get a FULL-BLEED banner: it
starts at x=0 and spans the whole body (no black bars from the list's 16 px
margins). Run: env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_hero.py"""
import json, os, sys, tempfile, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD", "caps": "ZUNE HD", "version": "0.1.0"})
os.environ["ZTOS_APP_ROOT"] = REPO
from PySide6.QtWidgets import QApplication
from tests.fake_slipmatd import FakeSlipmatd

def pump(app, s):
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.02)

def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-hero-")
    os.environ["XDG_RUNTIME_DIR"] = tmp
    srv = FakeSlipmatd(os.path.join(tmp, "slipmat.sock"), stage="ready"); srv.start()
    import ztos, hub, client
    client.backend.connect(ready_timeout=5.0); pump(app, 0.4)
    zapp = ztos.App(); music = hub.MusicHub(zapp)
    zapp.stack.append(music); zapp._place(music)
    zapp.window.resize(360, 640); music.resize(360, 640); zapp.window.show(); pump(app, 1.0)
    fails = []
    for kind, id_ in (("libraryAlbum", "al.fix1"), ("libraryArtist", "ar.fix1"), ("libraryPlaylist", "pl.fix1")):
        zapp.push(hub.DetailPage(kind, id_)); pump(app, 1.5)
        page = zapp.page
        print(kind, type(page).__name__, page.isVisible(), len(page._entries), page.header.isVisible())
        hero = getattr(page, "_hero", None)
        if hero is None:
            fails.append(f"{kind}: no hero"); zapp.pop(); pump(app, 0.5); continue
        g = hero.geometry()
        if g.x() != 0 or g.width() != page.body.width() or g.width() < 300:
            fails.append(f"{kind}: hero not full-bleed x={g.x()} w={g.width()} body={page.body.width()}")
        zapp.pop(); pump(app, 0.5)
    srv.stop()
    print("ALL PASS" if not fails else "FAILED: " + "; ".join(fails))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.stdout.flush(); rc = main(); sys.stdout.flush(); os._exit(rc)
