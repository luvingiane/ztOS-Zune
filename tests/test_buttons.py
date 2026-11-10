"""CircleButton: pressing must not start the GL lean (the opaque full-rect
black quad = the square overlay on round buttons), yet taps still work and the
ring still fills (press state). Run:
  env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_buttons.py"""
import json, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".sdk", "ztos", "sdk", "runtime"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZTOS_MANIFEST"] = json.dumps({"id": "dev.oneplus2.zunehd", "name": "Zune HD", "caps": "ZUNE HD", "version": "0.1.0"})
os.environ["ZTOS_APP_ROOT"] = REPO
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
import ztos, icons
from widgets import CircleButton

app = QApplication.instance() or QApplication([])
host = QWidget(); host.resize(360, 640)
taps = []
b = CircleButton(icons.path("play"), "x", lambda: taps.append(1)); b.setParent(host)
host.show()
calls = []
orig = ztos.RoundButton._lean_begin
ztos.RoundButton._lean_begin = lambda self: calls.append(1)   # would be the SDK path
# CircleButton overrides it, so the SDK one must never run
QTest.mousePress(b, Qt.LeftButton, Qt.NoModifier, QPoint(34, 26))
ok = True
if calls or b._gl_lean:
    print("FAIL: lean started on press"); ok = False
if not b._p_to > 0:
    print("FAIL: press state not set"); ok = False
QTest.mouseRelease(b, Qt.LeftButton, Qt.NoModifier, QPoint(34, 26))
if taps != [1]:
    print("FAIL: tap not delivered", taps); ok = False
plain = ztos.RoundButton(icons.path("play"), "x"); plain.setParent(host)
QTest.mousePress(plain, Qt.LeftButton, Qt.NoModifier, QPoint(34, 26))
if not calls:
    print("FAIL: control (plain RoundButton) did not start the lean - test is blind"); ok = False
ztos.RoundButton._lean_begin = orig
print("ALL PASS" if ok else "FAILED"); sys.exit(0 if ok else 1)
