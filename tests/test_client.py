"""Tests for client.py against a fake slipmatd (tests/fake_slipmatd.py) with
the anonymized fixtures in tests/fixtures/ — the real samples in
~/oneplus2/docs/zune-real-samples.txt are NEVER copied here.

Covers the stage-3 fixes: correct per-view mapping (artist name not genres,
album name not title-less squares), live-only data when stage=ready, an empty
state when the daemon is missing, sort params on the wire, songs+"added" joined
through the albums' date_added, search results, open page, snapshot/queue.

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin python3 tests/test_client.py
"""
import json
import os
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from PySide6.QtCore import QCoreApplication

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
    app = QCoreApplication([])
    tmp = tempfile.mkdtemp(prefix="zunehd-test-")
    os.environ["XDG_RUNTIME_DIR"] = tmp
    sock = os.path.join(tmp, "slipmat.sock")
    log = os.path.join(tmp, "requests.log")

    # --- daemon running and ready: live data only, correct mapping ----------
    srv = FakeSlipmatd(sock, requests_log=log, stage="ready")
    srv.start()

    import client
    b = client.Backend()
    check("connect ready", b.connect(ready_timeout=5.0) and b.live, f"stage={b.stage}")
    pump(app, 0.5)

    artists = b.browse("artists")
    check("artists mapped: name is title", [a["title"] for a in artists] ==
          ["Fixture Artist A", "Fixture Artist B", "Fixture Artist C (catalog)"],
          str([a["title"] for a in artists]))
    check("artists subtitle is genres", artists[0]["subtitle"] == "Fixture Pop")
    check("artists artwork template kept", artists[0]["artworkTemplate"].startswith("https://art.example.invalid"))

    albums = b.browse("albums", "added", reverse=False)
    check("albums sorted by added desc (natural)", [a["title"] for a in albums][0] == "Fixture Album A",
          str([a["title"] for a in albums]))
    check("album has trackCount/dateAdded", albums[0]["trackCount"] == 6 and albums[0]["dateAdded"].startswith("2024"))

    songs = b.browse("songs", "title")
    check("songs mapped: title/subtitle/duration", songs[0]["title"] == "Fixture Song One"
          and "Fixture Artist A" in songs[0]["subtitle"] and songs[0]["durationMs"] == 174000)
    song_two = next(s for s in songs if s["title"] == "Fixture Song Two")
    check("song catalog_id null -> not playable", song_two["playable"] is False and song_two["catalogId"] == "")
    check("song dateAdded empty (Apple sends none for songs)", songs[0]["dateAdded"] == "")

    # songs + "added": client-side join through the albums' date_added
    songs_added = b.browse("songs", "added")
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    browse_songs = [r for r in reqs if r.get("req") == "browse" and r.get("view") == "songs"]
    check("songs+added never asks the daemon for added (not offered)",
          all(r.get("sort") != "added" for r in browse_songs))
    check("songs+added ordered by album date_added", [s["title"] for s in songs_added][0] == "Fixture Song One",
          str([s["title"] for s in songs_added]))

    # sort params go on the wire
    b.browse("albums", "year", reverse=True)
    reqs = [json.loads(l) for l in open(log)]
    alb = [r for r in reqs if r.get("req") == "browse" and r.get("view") == "albums"]
    check("browse sends sort+reverse on the wire", any(r.get("sort") == "year" and r.get("reverse") is True for r in alb))

    results = b.search("fixture", "all")
    check("search results mapped", len(results) == 1 and results[0]["title"] == "Fixture Song One")
    reqs = [json.loads(l) for l in open(log)]
    check("search req on the wire with filter", any(r.get("req") == "search" and r.get("filter") == "all" for r in reqs))

    header, entries = b.open_page("libraryAlbum", "al.fix1")
    check("open_page returns header+entries", header is not None and header["title"] == "Fixture Album A"
          and len(entries) == 1)

    np = b.now_playing()
    check("snapshot -> now_playing", np["title"] == "Fixture Song One" and np["playing"] is True
          and abs(np["volume"] - 0.8) < 1e-6 and np["art_path"].endswith("fixture-art.jpg"))
    items, pos = b.queue_items()
    check("queue event -> items/position", len(items) == 2 and pos == 0 and items[0]["title"] == "Fixture Song One")

    # play like the original client: ids = catalog ids of the whole list,
    # index = position among sendable rows, start = "clicked"
    songs_rows = b.browse("songs", "title")
    sent, reason = b.play_list(songs_rows, 0)
    pump(app, 0.5)
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    play_reqs = [r for r in reqs if r.get("req") == "play"]
    check("play sends catalog ids of the list + index + start=clicked",
          sent and play_reqs and play_reqs[-1].get("ids") == ["c.fix1", "c.fix3"]
          and play_reqs[-1].get("index") == 0 and play_reqs[-1].get("start") == "clicked",
          str(play_reqs[-1] if play_reqs else None))
    # tapped row without catalog_id (library-only, not streamable): plays the
    # NEXT available row, with a note; the library id is never sent
    unplay_idx = next(i for i, r in enumerate(songs_rows) if not r.get("catalogId"))
    rot = [songs_rows[unplay_idx]] + [r for i, r in enumerate(songs_rows) if i != unplay_idx]
    sent2, note2 = b.play_list(rot, 0)   # Fixture Song Two has catalog_id null, put first
    pump(app, 0.5)
    play_reqs = [json.loads(l) for l in open(log) if json.loads(l).get("req") == "play"]
    check("unavailable row -> starts from next available + note, library id NOT sent",
          sent2 and note2 and "not available" in note2 and play_reqs[-1].get("ids") == ["c.fix1", "c.fix3"]
          and play_reqs[-1].get("index") == 0, f"idx={unplay_idx} {note2} {play_reqs[-1]}")
    check("no play req with library id i.fix2",
          all("i.fix2" not in (r.get("ids") or []) for r in play_reqs))
    # daemon-learned unplayable ids (unplayable.json) are filtered out of the play list
    cdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(cdir, "slipmat"))
    with open(os.path.join(cdir, "slipmat", "unplayable.json"), "w") as f:
        json.dump(["c.fix3"], f)
    os.environ["XDG_CACHE_HOME"] = cdir
    check("is_available: id in unplayable.json is unavailable",
          not client.is_available(next(r for r in songs_rows if r.get("catalogId") == "c.fix3"))
          and client.is_available(next(r for r in songs_rows if r.get("catalogId") == "c.fix1"))
          and not client.is_available(songs_rows[unplay_idx]))
    sent3, _ = b.play_list(songs_rows, 0)
    pump(app, 0.5)
    play_reqs = [json.loads(l) for l in open(log) if json.loads(l).get("req") == "play"]
    check("play list excludes unplayable.json ids", sent3 and play_reqs[-1].get("ids") == ["c.fix1"],
          str(play_reqs[-1]))
    os.environ.pop("XDG_CACHE_HOME")

    # writes go out on the wire (no response -> give the server thread a beat)
    b.write("favorite", "c.fix1")
    b.transport("setVolume", volume=0.5)
    b.transport("setShuffle", shuffle=True)
    pump(app, 0.6)
    reqs = [json.loads(l) for l in open(log)]
    check("write/transport on the wire", any(r.get("req") == "write" and r.get("action") == "favorite" for r in reqs)
          and any(r.get("req") == "transport" and r.get("cmd") == "setVolume" for r in reqs)
          and any(r.get("req") == "transport" and r.get("cmd") == "setShuffle" for r in reqs))

    srv.stop()
    try:
        b._client.close()
    except Exception:
        pass

    # --- daemon missing: empty state, with a notice ------------------
    os.unlink(sock)
    b2 = client.Backend()
    check("no socket -> not live", not b2.connect() and not b2.live)
    check("offline notice shown", b2.status_notice.startswith("slipmatd"), b2.status_notice)
    check("no daemon -> no rows (no sample data)", b2.browse("artists") == [] and b2.search("a") == []
          and b2.queue_items() == ([], 0) and not b2.now_playing()["title"])

    # --- daemon present but signedOut: empty with notice, never mixed ---------
    srv2 = FakeSlipmatd(sock, stage="signedOut")
    srv2.start()
    b3 = client.Backend()
    b3.connect(ready_timeout=3.0)
    pump(app, 0.3)
    check("signedOut -> not live", not b3.live, f"stage={b3.stage}")
    check("signedOut notice", "signedOut" in b3.status_notice, b3.status_notice)
    check("signedOut -> no rows at all", b3.browse("songs") == [])
    srv2.stop()
    try:
        b3._client.close()
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
