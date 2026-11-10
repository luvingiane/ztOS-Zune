"""Search grouped by category + artist page (albums). Uses the fake daemon for
connection and patches backend.search/open_page_async with mixed entries (the
shape verified on B: an artist `open` returns ALBUM entries).
Run: env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_search.py"""
import json, os, sys, tempfile, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD", "caps": "ZUNE HD", "version": "0.1.0"})
os.environ["ZTOS_APP_ROOT"] = REPO
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from tests.fake_slipmatd import FakeSlipmatd

FAILS = []
def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name, extra)
    if not ok: FAILS.append(name)
def pump(app, s):
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.02)

def song(i, cid="c%d"):
    return {"kind": "song", "title": f"Song {i}", "subtitle": "A — B", "durationMs": 1000, "id": f"i.{i}",
            "catalogId": (cid % i) if cid else "", "artworkTemplate": "", "raw": {"k": 1}}
def alb(i): return {"kind": "album", "title": f"Album {i}", "subtitle": "A · 2020", "id": f"al{i}", "pageKind": "album", "artworkTemplate": ""}
def art(i): return {"kind": "artist", "title": f"Artist {i}", "subtitle": "Pop", "id": f"ar{i}", "pageKind": "artist", "artworkTemplate": ""}
def pl(i): return {"kind": "playlist", "title": f"Playlist {i}", "subtitle": "me", "id": f"pl{i}", "pageKind": "playlist", "artworkTemplate": ""}

def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-search-")
    os.environ["XDG_RUNTIME_DIR"] = tmp
    srv = FakeSlipmatd(os.path.join(tmp, "slipmat.sock"), stage="ready"); srv.start()
    import ztos, screens, hub, client
    client.backend.connect(ready_timeout=5.0); pump(app, 0.4)
    zapp = ztos.App()
    first = ztos.Page("hub"); zapp.stack = [first]; zapp._place(first)
    zapp.window.resize(360, 640); zapp.window.show()

    check("group_results order artists/albums/songs/playlists",
          [k for k, _h, _r in screens.group_results([song(1), pl(1), alb(1), art(1)])] == ["artist", "album", "song", "playlist"])

    page = screens.SearchPage(); zapp.push(page); page.resize(360, 640); pump(app, 1.0)
    mixed = [art(1), alb(1), alb(2), song(1), song(2, ""), song(3), song(4), song(5), song(6), song(7), pl(1)]
    client.backend.search = lambda q, f="all", **k: [r for r in mixed if f == "all" or r["kind"] + "s" == f]
    page._box.field.setText("x"); page._run(); pump(app, 0.3)
    heads = [w.text() for w in (page.list.itemAt(i).widget() for i in range(page.list.count())) if w is not None and w.__class__.__name__ == "QLabel" and w.text()]
    check("section headers shown in order", heads[-4:] == ["artists", "albums", "songs", "playlists"] or heads == ["artists", "albums", "songs", "playlists"], str(heads))
    rows = [w for w in (page.list.itemAt(i).widget() for i in range(page.list.count())) if w is not None and w.__class__.__name__ == "Row"]
    titles = [r._title for r in rows]
    check("'all' caps songs at 6 and adds 'see all songs'", "see all songs" in titles and "Song 7" not in titles, str(titles))
    unavail = [r for r in rows if r._title == "Song 2"]
    check("song without catalog id is marked unavailable", unavail and not unavail[0]._available)
    page._set_filter("songs"); page._debounce.stop(); page._run(); pump(app, 0.2)
    rows = [w for w in (page.list.itemAt(i).widget() for i in range(page.list.count())) if w is not None and w.__class__.__name__ == "Row"]
    check("filter songs: only songs, all 7", len(rows) == 7 and all(r._title.startswith("Song") for r in rows), str([r._title for r in rows]))
    page._set_filter("all")

    # artist page: hero + top songs (catalog search by name) + latest release +
    # albums / singles grids; album rows open pages; song hold -> context menu
    header = {"kind": "artist", "title": "Artist 1", "subtitle": "Pop", "artworkTemplate": "", "id": "ar1"}
    albs = [dict(alb(1), year="2019"), dict(alb(2), year="2023"), dict(alb(3), title="Hit - Single", year="2024")]
    client.backend.open_page_async = lambda kind, id_, cb: QTimer.singleShot(80, lambda: cb(header, albs))
    songs = [dict(song(i), artist="Artist 1 & Friend") for i in (1, 2)] + [dict(song(9), artist="Someone Else")]
    client.backend.search_async = lambda q, f, cb: QTimer.singleShot(120, lambda: cb(songs))
    d = hub.DetailPage("artist", "ar1", "Artist 1"); zapp.push(d); d.resize(360, 640); pump(app, 1.0)
    if d.list.count() <= 2: d.shown(); pump(app, 0.8)
    kinds = [type(d.list.itemAt(i).widget()).__name__ for i in range(d.list.count())]
    rows = [w for w in (d.list.itemAt(i).widget() for i in range(d.list.count())) if w is not None and w.__class__.__name__ == "Row"]
    titles = [r._title for r in rows]
    check("artist page has the hero and two album grids (albums, singles)",
          kinds.count("ArtistHero") == 1 and kinds.count("AlbumGrid") == 2, str(kinds))
    check("top songs = songs by this artist only (filtered), no 'Someone Else'",
          "Song 1" in titles and "Song 2" in titles and "Song 9" not in titles, str(titles))
    check("latest release row is the newest (singles included, suffix trimmed)", "Hit" in titles, str(titles))
    if os.environ.get("SHOT"):
        zapp.window.grab().save(os.environ["SHOT"] + "-0.png")
        d.scroll_to(520); pump(app, 0.4)
        zapp.window.grab().save(os.environ["SHOT"] + "-1.png")
        d.scroll_to(0)
    pushed = []
    zapp.push = lambda p: pushed.append(p)
    next(r for r in rows if r._title == "Hit").tapped.emit()
    check("tapping the latest release opens its page", pushed and isinstance(pushed[0], hub.DetailPage) and pushed[0]._kind == "album")
    menus = []
    orig_menu = ztos.menu
    ztos.menu = lambda anchor, items: menus.append([l for l, _ in items])
    next(r for r in rows if r._title == "Song 1").held.emit()
    ztos.menu = orig_menu
    check("hold on a song row opens the context menu", menus and "add to queue" in menus[0], str(menus))
    print("ALL PASS" if not FAILS else f"FAILED: {FAILS}")
    return 1 if FAILS else 0

if __name__ == "__main__":
    os._exit(main())
