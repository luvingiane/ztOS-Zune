"""RowWarmer/warm_cache must only touch row-sized widgets: the albums grid is
ONE tall Entry (140 px per 3 albums); a full-DPR pixmap of it is tens of Mpx
(B: 1.1 GB RES, GUI blocked, taps on albums dead). Run:
  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=3 python3 tests/test_warm.py"""
import json, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD", "caps": "ZUNE HD", "version": "0.1.0"})
os.environ["ZTOS_APP_ROOT"] = REPO
from PySide6.QtWidgets import QApplication
import ztos, widgets
from hub import AlbumGrid

app = QApplication.instance() or QApplication([])
grid = AlbumGrid([{"title": f"a{i}", "id": str(i)} for i in range(400)], on_tap=lambda al: None)
grid.resize(360, grid.height())
row = widgets.Row("t", "s")
row.resize(360, widgets.ROW_H)
ok = True
if widgets.warm_cache(grid) or getattr(grid, "_cache", None) is not None:
    print("FAIL: tall grid got a cache pixmap (%d px high)" % grid.height()); ok = False
if not widgets.warm_cache(row):
    print("FAIL: a normal row is no longer warmed"); ok = False
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
host = QWidget(); host.resize(360, 640)
got = []
g2 = AlbumGrid([{"title": f"a{i}", "id": str(i)} for i in range(9)], on_tap=lambda al: got.append(al["id"]))
g2.setParent(host); g2.resize(360, g2.height()); g2.build_cells(); host.show()
w = g2.childAt(60, 60)
QTest.mouseClick(w or g2, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
if got != ["0"]:
    print("FAIL: tap on a grid cover did not open the album", got, type(w).__name__); ok = False
print("PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
