"""Test that the artwork fetcher REALLY downloads and decodes an image.

Local HTTP server serves one small generated JPEG at /art/<w>x<h>bb.jpg;
the fetcher must fetch it (template resolution {w}x{h}), write the disk
cache, emit done, and Artwork must swap in a non-null QImage. A 404 template
must fail cleanly (ok=False, clear log, no crash). This test fails if the
fetcher thread never starts (the QThread.create bug seen on the phone).

Run:  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_art.py
"""
import http.server
import json
import os
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD"})
os.environ["ZTOS_APP_ROOT"] = REPO

from PySide6.QtWidgets import QApplication
from PIL import Image

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
    tmp = tempfile.mkdtemp(prefix="zunehd-art-")
    os.environ["XDG_CACHE_HOME"] = tmp          # art.CACHE_DIR is computed at import: patch it
    import art
    art.CACHE_DIR = os.path.join(tmp, "artwork")

    # one real JPEG served over HTTP
    img = Image.new("RGB", (64, 64), (200, 30, 90))
    buf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(buf.name, "JPEG")
    payload = open(buf.name, "rb").read()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/art/"):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    import ztos
    zapp = ztos.App()

    template = f"http://127.0.0.1:{port}/art/{{w}}x{{h}}bb.jpg"
    results = []
    art._fetcher.done.connect(lambda t, p, ok: results.append((t, p, ok)))

    w = art.Artwork(48, "test", template, art_size=300)
    w.resize(48, 48)
    w.show()
    check("fetcher thread started", art._fetcher._thread.isRunning() or bool(results),
          f"running={art._fetcher._thread.isRunning()}")
    pump(app, 3.0)

    ok_hits = [r for r in results if r[2]]
    check("download succeeded (done ok=True)", bool(ok_hits), str(results))
    cached = art.cache_path(template, 300)
    check("disk cache file written", os.path.exists(cached), cached)
    img2 = art.image_for(cached)
    check("cached file decodes to a real image", img2 is not None and not img2.isNull()
          and img2.width() == 64, f"{img2.width() if img2 else None}x{img2.height() if img2 else None}")
    pump(app, 0.5)
    check("Artwork swapped in the image", w._img is not None and not w._img.isNull())

    # 404 template: clean failure, no crash
    results.clear()
    bad = f"http://127.0.0.1:{port}/missing/{{w}}x{{h}}bb.jpg"
    art._fetcher.add(bad, 300)
    pump(app, 2.0)
    check("404 -> done ok=False, no exception", any(not r[2] for r in results), str(results))

    srv.shutdown()
    print()
    if FAILED:
        print("FAILED:", FAILED)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
