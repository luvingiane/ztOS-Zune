"""Scroll benchmark (offscreen): a Page with N rows, fling-scrolled step by
step; reports ms per scroll frame. Imitates the phone cost directionally —
the declared scale factor to A53@1.5GHz is ~8x (desktop core here vs small
core + tiny cache; NOT a precise estimate, see STATO.md).

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/bench_scroll.py [N]
"""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD"})
os.environ["ZTOS_APP_ROOT"] = REPO

from PySide6.QtWidgets import QApplication

import library


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    app = QApplication([])
    import ztos
    import widgets
    zapp = ztos.App()
    page = ztos.Page("bench", header=False)
    page.list.setContentsMargins(17, 0, 16, 24)
    songs = []
    for i in range(n):
        songs.append({"kind": "song", "title": f"Song {i}", "subtitle": "Artist — Album",
                      "artist": "Artist", "album": "Album", "duration_ms": 180000,
                      "id": f"bench-{i}", "catalogId": f"c{i}"})
    # one artwork template shared by all rows, pre-seeded in the disk cache:
    # during scroll we "deliver" it progressively, like the fetcher would
    import art
    from PIL import Image
    os.makedirs(art.CACHE_DIR, exist_ok=True)
    tpl = "bench://art/{w}x{h}bb.jpg"
    art_path = art.cache_path(tpl, 300)
    Image.new("RGB", (300, 300), (120, 40, 160)).save(art_path, "JPEG")
    for s in songs:
        page.add(widgets.Row(s["title"], s["subtitle"], s["duration_ms"], art=tpl))
    zapp.stack.append(page)
    zapp._place(page)
    zapp.window.resize(360, 640)
    zapp.window.show()

    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(1.0)
    if os.environ.get("WARM"):                      # RowWarmer's effect, all rows warmed
        t0 = time.perf_counter()
        n_w = sum(1 for r in page.findChildren(widgets.Row) if widgets.warm_cache(r))
        print(f"warmed {n_w} rows in {(time.perf_counter()-t0)*1000:.0f} ms (idle time, off the scroll)")
    max_scroll = page._max()
    steps = 240
    times = []
    delivered = False
    for i in range(steps):
        t0 = time.perf_counter()
        page._set(max_scroll * i / steps)
        if not delivered and i > steps // 3:
            art._fetcher.done.emit(tpl, art_path, True)   # artwork arrives mid-scroll
            delivered = True
        app.processEvents()
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    avg = sum(times) / len(times)
    print(f"bench: {n} rows, {steps} scroll steps")
    print(f"ms/frame: avg={avg:.2f} p50={times[len(times)//2]:.2f} p95={times[int(len(times)*0.95)]:.2f} max={times[-1]:.2f}")
    print(f"=> at 8x A53 scale: avg={avg*8:.0f} ms/frame (~{1000/(avg*8):.0f} fps ceiling)" if avg > 0 else "")
    print("target: <= 3 ms/frame on PC (<= 24 ms on A53 at 8x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
