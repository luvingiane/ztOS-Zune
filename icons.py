"""Vector glyphs, drawn ONCE here and used everywhere (player controls,
detail-page actions, options menu) — no duplicated icon code anywhere else.

All glyphs are QPainterPath strokes/fills around (0,0), `size` across, white
by default; crisp at any size (vector, never a scaled bitmap).
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


def draw_glyph(p: QPainter, name: str, size: float, color=None):
    """Draw glyph `name` centered at the painter's origin, `size` px across."""
    p.save()
    pen = QPen(color or QColor("white"), max(1.6, size / 11.0),
               Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(color or QColor("white"))
    s = size / 2.0
    if name == "play":
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(-s * 0.45, -s * 0.85), QPointF(-s * 0.45, s * 0.85),
                       QPointF(s * 0.9, 0)])
    elif name == "pause":
        p.setPen(Qt.NoPen)
        w = s * 0.55
        p.drawRect(QRectF(-s * 0.85, -s * 0.85, w, 2 * s * 0.85))
        p.drawRect(QRectF(s * 0.85 - w, -s * 0.85, w, 2 * s * 0.85))
    elif name == "prev":
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(-s, -s * 0.85, s * 0.25, s * 1.7))
        p.drawPolygon([QPointF(s * 0.85, -s * 0.85), QPointF(s * 0.85, s * 0.85),
                       QPointF(-s * 0.5, 0)])
    elif name == "next":
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(s * 0.75, -s * 0.85, s * 0.25, s * 1.7))
        p.drawPolygon([QPointF(-s * 0.85, -s * 0.85), QPointF(-s * 0.85, s * 0.85),
                       QPointF(s * 0.5, 0)])
    elif name == "shuffle":
        # two crossing arrows with heads (standard media shuffle)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(-s, -s * 0.45), QPointF(s * 0.55, -s * 0.45))
        p.drawLine(QPointF(-s, s * 0.45), QPointF(s * 0.55, s * 0.45))
        p.drawLine(QPointF(-s * 0.35, -s * 0.45), QPointF(s * 0.15, s * 0.45))
        p.drawLine(QPointF(-s * 0.35, s * 0.45), QPointF(s * 0.15, -s * 0.45))
        p.setBrush(color or QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(s * 0.85, -s * 0.45), QPointF(s * 0.25, -s * 0.75),
                       QPointF(s * 0.25, -s * 0.15)])
        p.drawPolygon([QPointF(s * 0.85, s * 0.45), QPointF(s * 0.25, s * 0.75),
                       QPointF(s * 0.25, s * 0.15)])
    elif name == "queue":
        # playlist: three lines + play triangle at the bottom right
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for yy in (-s * 0.62, -s * 0.1, s * 0.42):
            p.drawLine(QPointF(-s * 0.85, yy), QPointF(s * 0.55, yy))
        p.setBrush(color or QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(s * 0.1, s * 0.18), QPointF(s * 0.1, s * 0.88),
                       QPointF(s * 0.85, s * 0.53)])
    elif name == "more":
        p.setPen(Qt.NoPen)
        for xx in (-s * 0.6, 0.0, s * 0.6):
            p.drawEllipse(QPointF(xx, 0), size / 9.0, size / 9.0)
    elif name == "star":
        path = QPainterPath()
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = s if i % 2 == 0 else s * 0.45
            (path.lineTo if i else path.moveTo)(math.cos(ang) * r, math.sin(ang) * r)
        path.closeSubpath()
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    elif name == "album":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(-s * 0.8, -s * 0.8, s * 1.6, s * 1.6))
        p.drawEllipse(QPointF(0, 0), s * 0.32, s * 0.32)
    elif name == "artist":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, -s * 0.45), s * 0.35, s * 0.35)
        p.drawArc(QRectF(-s * 0.7, -s * 0.1, s * 1.4, s * 1.4), 0, 180 * 16)
    elif name == "repeat":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-s * 0.8, -s * 0.8, s * 1.6, s * 1.6), 30 * 16, 300 * 16)
        p.setBrush(color or QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(s * 0.75, -s * 0.1), QPointF(s * 0.95, -s * 0.35),
                       QPointF(s * 0.55, -s * 0.45)])
    elif name == "search":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(-s * 0.1, -s * 0.15), s * 0.62, s * 0.62)
        p.drawLine(QPointF(s * 0.4, s * 0.35), QPointF(s * 0.95, s * 0.9))
    elif name == "sort":
        # up/down arrows (sort control)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(-s * 0.5, -s * 0.8), QPointF(-s * 0.5, s * 0.8))
        p.drawLine(QPointF(s * 0.5, s * 0.8), QPointF(s * 0.5, -s * 0.8))
        p.setBrush(color or QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(-s * 0.5, -s * 0.95), QPointF(-s * 0.85, -s * 0.45),
                       QPointF(-s * 0.15, -s * 0.45)])
        p.drawPolygon([QPointF(s * 0.5, s * 0.95), QPointF(s * 0.85, s * 0.45),
                       QPointF(s * 0.15, s * 0.45)])
    elif name == "delete":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(-s * 0.7, -s * 0.45, s * 1.4, s * 1.15))
        p.drawLine(QPointF(-s * 0.85, -s * 0.7), QPointF(s * 0.85, -s * 0.7))
        p.drawLine(QPointF(-s * 0.25, -s * 0.7), QPointF(-s * 0.25, -s * 0.45))
        p.drawLine(QPointF(s * 0.25, -s * 0.7), QPointF(s * 0.25, -s * 0.45))
    else:
        raise ValueError(f"unknown glyph {name!r}")
    p.restore()
