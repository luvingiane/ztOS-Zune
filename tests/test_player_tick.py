"""Regression test for the 'seek bar jumps every ~2 s on B' bug: slipmatd
publishes a snapshot every 500 ms while playing (serve.rs:39 TICK_MS=500),
and NowPlaying._refresh -> PlayerView.set_track used to invalidate the whole
page cache (redraw + content_changed + _bg_full=None -> blur recompute) on
EVERY snapshot. On the phone that saturates the GUI thread and the visible
bar jumps in ~2 s steps.

This test streams fake snapshots at 500 ms cadence (position advancing, same
track) and asserts: no PlayerView.redraw/content_changed, no blur recompute,
seek.update() IS called. It FAILS on the pre-fix code.

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_player_tick.py
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

from PySide6.QtWidgets import QApplication

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
    tmp = tempfile.mkdtemp(prefix="zunehd-tick-")
    os.environ["HOME"] = tmp
    os.environ["XDG_RUNTIME_DIR"] = tmp

    import ztos
    import player
    zapp = ztos.App()
    first = ztos.Page("hub")
    zapp.stack.append(first)
    zapp._place(first)
    page = player.NowPlaying(zapp)
    zapp.push(page)
    zapp.window.resize(360, 640)
    zapp.window.show()
    pump(app, 1.0)

    view = page.view
    # spies
    calls = {"redraw": 0, "content_changed": 0, "bg": 0}
    orig_redraw = view.update
    orig_cc = view.update
    orig_bg = player.make_blur_bg

    def spy_redraw():
        calls["redraw"] += 1
        return orig_redraw()

    def spy_cc():
        calls["content_changed"] += 1
        return orig_cc()

    def spy_bg(*a, **k):
        calls["bg"] += 1
        return orig_bg(*a, **k)

    view.update = spy_redraw
    player.make_blur_bg = spy_bg

    seek_updates = [0]
    orig_pos = view._seek.set_position
    view._seek.set_position = lambda *a, **k: (seek_updates.__setitem__(0, seek_updates[0] + 1), orig_pos(*a, **k))[1]
    label_sets = [0]
    orig_text = view._title.setText
    view._title.setText = lambda *a, **k: (label_sets.__setitem__(0, label_sets[0] + 1), orig_text(*a, **k))[1]

    # first snapshot: full track (metadata) — allowed to redraw once
    base = {"title": "Fixture Song", "artist": "Fixture Artist", "album": "Fixture Album",
            "track_id": "c.fix1", "duration_ms": 174000, "position_ms": 1000,
            "playing": True, "art_path": ""}
    view.set_track(dict(base))
    pump(app, 0.3)
    calls0 = dict(calls)
    check("first track set: texts set once", label_sets[0] == 1, str(label_sets))

    # now 8 snapshots at 500 ms cadence, same track, position advancing
    for i in range(8):
        snap = dict(base, position_ms=1000 + (i + 1) * 500)
        view.set_track(snap)
        pump(app, 0.05)

    check("position-only snapshots do NOT touch the texts/cover (no page work)",
          label_sets[0] == 1 and calls["redraw"] == calls0["redraw"], f"labels={label_sets[0]} redraw {calls0['redraw']}->{calls['redraw']}")
    check("blur background NOT recomputed per position snapshot",
          calls["bg"] == calls0["bg"], f"bg {calls0['bg']}->{calls['bg']}")
    check("seek bar still repaints (update called)", seek_updates[0] > 0,
          f"updates={seek_updates[0]}")
    check("position is monotonic and advanced",
          view._model.current() > 1.0, f"pos={view._model.current():.2f}")

    # track change -> full refresh allowed again
    view.set_track(dict(base, title="Another", track_id="c.fix2", position_ms=0))
    pump(app, 0.2)
    check("track change DOES refresh the texts", label_sets[0] == 2, str(label_sets))

    print()
    if FAILED:
        print("FAILED:", FAILED)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
