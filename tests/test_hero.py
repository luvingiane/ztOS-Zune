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
        if kind == "libraryAlbum":
            seen = []
            orig = ztos.menu
            ztos.menu = lambda anchor, items: seen.append([i[0] for i in items])
            page._more_menu(); ztos.menu = orig
            if not seen or "view artist" not in seen[0]:
                fails.append(f"album more-menu lacks 'view artist': {seen}")
            if page._artist_name() != "Fixture Artist A":
                fails.append(f"album artist name wrong: {page._artist_name()!r}")
        zapp.pop(); pump(app, 0.5)
    srv.stop()
    import art
    f = art._Fetcher()
    for th in f._threads:
        th.isRunning = lambda: True            # no network: only the queue order is checked
    for i in range(3):
        f.add(f"http://x.invalid/{i}/{{w}}x{{h}}bb.jpg", 300)
    f.add("http://x.invalid/hero/{w}x{h}bb.jpg", 768, priority=True)
    if f._queue[0][1] != 768 or len(f._queue) != 4 or len(f._threads) < 2:
        fails.append(f"priority/pool broken: {f._queue} threads={len(f._threads)}")
    art.NOIMG = True
    if art.local_art(os.path.join(REPO, "icon.png")) is not None:
        fails.append("NOIMG: local_art still returns files")
    art.allow(os.path.join(REPO, "icon.png"))
    if art.local_art(os.path.join(REPO, "icon.png")) is None:
        fails.append("NOIMG: allowed artwork (playlist/now playing) is blocked")
    f2 = art._Fetcher()
    for th in f2._threads:
        th.isRunning = lambda: True
    f2.add("http://x.invalid/blocked/{w}x{h}bb.jpg", 300)
    if f2._queue:
        fails.append("NOIMG: a blocked template got queued for download")
    art.allow("http://x.invalid/ok/{w}x{h}bb.jpg")
    f2.add("http://x.invalid/ok/{w}x{h}bb.jpg", 300)
    if len(f2._queue) != 1:
        fails.append("NOIMG: allowed template not queued")
    art.NOIMG = False
    art.ALLOW.clear()
    if art.local_art(os.path.join(REPO, "icon.png")) is None:
        fails.append("local_art broken without NOIMG")
    import widgets
    art.set_covers(False)
    r = widgets.Row("t", "s", art="http://x.invalid/c/{w}x{h}bb.jpg")
    if r._tx != 0 or r.findChildren(widgets.Thumb):
        fails.append("covers off: row still has a thumb box")
    if not hub.albums_as_list():
        fails.append("covers off: albums should be a list")
    art.set_covers(True)
    r2 = widgets.Row("t", "s", art="http://x.invalid/c/{w}x{h}bb.jpg")
    if not r2.findChildren(widgets.Thumb):
        fails.append("covers on: row lost its thumb")
    if hub.albums_as_list():
        fails.append("covers on, setting off: albums should be a grid")
    print("ALL PASS" if not fails else "FAILED: " + "; ".join(fails))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.stdout.flush(); rc = main(); sys.stdout.flush(); os._exit(rc)
