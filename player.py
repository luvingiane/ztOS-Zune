"""Now Playing, rifatta dietro lo screenshot di riferimento del proprietario
(docs/shots/40-ref-nowplaying.png — osservato da: screenshot del proprietario
del 7/11, vedi PROVENANCE.md; no codice della demo letto/copiato).

Layout (360x640 logici, misurati sul riferimento):
- sfondo: gradiente scuro dai colori della copertina + parola gigante quasi
  trasparente (titolo del brano, ~180px light, alpha 0.10) — niente blur,
  niente texture a schermo intero (budget perf fase 3)
- copertina piccola 105x105 in alto a sinistra (16,22) con ombra semplice
- a destra: titolo in maiuscolo piccolo, album in grigio chiaro, artista in
  grande sottile (come nel riferimento)
- barra di avanzamento sottile con pallino bianco, tempo trascorso a sinistra
  e rimanente con il meno a destra ("-2:51")
- UNA riga di cinque controlli: coda, precedente, play/pausa (il più grande),
  successivo, opzioni — niente volume (tasti fisici), niente altro
- il menu Opzioni (stile pannello scuro ztOS, righe >= 48px, icona+testo+
  sottotesto) apre: preferiti, vai all'album, vai all'artista, shuffle,
  repeat. Le voci non fattibili (scarica, condividi, stazione, ecc.) sono
  documentate in PLAYER-OPTIONS.md e NON compaiono (niente voci finte).
"""
import ztos
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from art import Artwork, local_art, image_for
from client import backend, rtitle
from widgets import draw_cover, cover_colors, fmt_ms

COVER = 105
COVER_X, COVER_Y = 16, 22
TEXT_X = COVER_X + COVER + 14          # 135
SEEK_Y = 505
CTRL_Y = 568


class CtrlButton(ztos.RoundButton):
    """A round transport control: white ring + vector glyph (queue/prev/play/
    pause/next/more). `big` makes the play/pause one larger."""

    def __init__(self, kind: str, on_tap=None, size: int = 48):
        super().__init__("", on_tap=on_tap)
        self._kind = kind
        self.setFixedSize(size, size)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = min(self.width(), self.height()) / 2.0 - 3.0
        if self._p_to > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 110))
            p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor("white"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r - 1.1, r - 1.1)
        p.setPen(QPen(QColor("white"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor("white"))
        s = r * 0.52
        k = self._kind
        if k == "play":
            p.drawPolygon([QPointF(cx - s * 0.45, cy - s), QPointF(cx - s * 0.45, cy + s),
                           QPointF(cx + s * 0.9, cy)])
        elif k == "pause":
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(cx - s * 0.8, cy - s, s * 0.62, 2 * s))
            p.drawRect(QRectF(cx + s * 0.18, cy - s, s * 0.62, 2 * s))
        elif k == "prev":
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(cx - s, cy - s, s * 0.22, 2 * s))
            p.drawPolygon([QPointF(cx + s * 0.9, cy - s), QPointF(cx + s * 0.9, cy + s),
                           QPointF(cx - s * 0.55, cy)])
        elif k == "next":
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(cx + s * 0.78, cy - s, s * 0.22, 2 * s))
            p.drawPolygon([QPointF(cx - s * 0.9, cy - s), QPointF(cx - s * 0.9, cy + s),
                           QPointF(cx + s * 0.55, cy)])
        elif k == "queue":            # coda: list glyph
            p.setPen(QPen(QColor("white"), 2.0, Qt.SolidLine, Qt.RoundCap))
            for i, yy in enumerate((-s * 0.55, 0.0, s * 0.55)):
                p.drawLine(QPointF(cx - s, cy + yy), QPointF(cx + s, cy + yy))
            p.setBrush(QColor("white"))
            p.setPen(Qt.NoPen)
            p.drawPolygon([QPointF(cx - s * 0.2, cy - s * 0.85), QPointF(cx + s * 0.55, cy - s * 0.45),
                           QPointF(cx - s * 0.2, cy - s * 0.05)])
        elif k == "more":             # opzioni: tre punti
            p.setBrush(QColor("white"))
            p.setPen(Qt.NoPen)
            for xx in (-s * 0.6, 0.0, s * 0.6):
                p.drawEllipse(QPointF(cx + xx, cy), 2.2, 2.2)


class PlayerSeek(QWidget):
    """Thin seek bar: white dot on a 3px track, elapsed left, '-remaining' right."""

    def __init__(self, on_seek=None):
        super().__init__()
        self.setFixedHeight(36)
        self._pos, self._dur = 0.0, 0.0
        self._seeking = False
        self._scrub = 0.0
        self._on_seek = on_seek

    def set_times(self, pos_ms, dur_ms):
        if not self._seeking:
            self._pos, self._dur = pos_ms / 1000.0, dur_ms / 1000.0
            self.update()

    def _frac(self):
        return 0.0 if self._dur <= 0 else min(1.0, (self._scrub if self._seeking else self._pos) / self._dur)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        w = float(self.width())
        y = 6.0
        f = self._frac()
        p.fillRect(QRectF(0, y, w, 3), QColor(255, 255, 255, 60))
        p.fillRect(QRectF(0, y, w * f, 3), QColor("white"))
        p.setBrush(ztos.accent())                  # accent dot, ztSettings color
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(w * f, y + 1.5), 5.5, 5.5)
        p.setPen(QColor(255, 255, 255, 170))
        p.setFont(ztos._font(ztos.FONT_REGULAR, 13))
        fm = QFontMetricsF(p.font())
        elapsed = fmt_ms(self._pos * 1000) if not self._seeking else fmt_ms(self._scrub * 1000)
        remaining = fmt_ms(max(0.0, self._dur - (self._scrub if self._seeking else self._pos)) * 1000)
        p.drawText(QPointF(0, 30), elapsed)
        p.drawText(QPointF(w - fm.horizontalAdvance("-" + remaining), 30), "-" + remaining)

    def mousePressEvent(self, event):
        self._seeking = True
        self._scrub = self._x(event.position().x())
        ztos.haptic("tick")
        self.update()

    def mouseMoveEvent(self, event):
        if self._seeking:
            self._scrub = self._x(event.position().x())
            self.update()

    def mouseReleaseEvent(self, event):
        if self._seeking:
            self._seeking = False
            self._pos = self._scrub
            ztos.haptic("tap")
            if self._on_seek:
                self._on_seek(self._scrub)
            self.update()

    def _x(self, x):
        return 0.0 if self._dur <= 0 else max(0.0, min(1.0, x / max(1.0, self.width()))) * self._dur


# ztOS shell chrome over the app window (ztmetro/ztmetro.c:128-131):
# STATUS_H = 28 top, NAV_BAR_H = 40 bottom. The player must fit inside this.
TOP_INSET = 28
BOTTOM_INSET = 40


class PlayerView(ztos.Entry):
    """Now Playing in metro key (owner: inspired by the original Slipmat
    client with the wrapper theme, NOT a copy of the Zune demo screenshot):
    big centered cover with a small shadow, blurred cover as background
    (computed once per track: cover downscaled to 24x42, then upscaled to the
    window — one small static image, no per-frame blur, no full-screen texture),
    title thin + artist — album grey with ellipsis, one thin seek bar with an
    accent dot (elapsed left, -remaining right), no volume, and the five
    controls `queue prev play/pause next options` fully inside the usable area
    (window minus status bar and nav bar)."""

    def __init__(self, app):
        super().__init__("", "")
        self._app = app
        self._track = {}
        self._bg_small = None          # 24x42 blurred cover, cached per track
        # controls: coda, prev, play/pausa (grande), next, opzioni
        self.ctrl = {}
        sizes = {"queue": 46, "prev": 48, "play": 64, "next": 48, "more": 46}
        for kind, cb in (("queue", lambda: app.push(_queue_page())),
                         ("prev", lambda: backend.transport("previous")),
                         ("play", lambda: backend.transport("playPause")),
                         ("next", lambda: backend.transport("next")),
                         ("more", self._open_options)):
            b = CtrlButton(kind, on_tap=cb, size=sizes[kind])
            b.setParent(self)
            self.ctrl[kind] = b
        self._seek = PlayerSeek(on_seek=lambda s: backend.seek(s * 1000.0))
        self._seek.setParent(self)
        self._cover = Artwork(300, "", "", art_size=512)
        self._cover.setParent(self)
        self._options = None
        self._ticker = QTimer(self, interval=1000)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start()
        self._layout()

    def _usable(self):
        win = self.window()
        w = win.width() if win.width() > 1 else self.width()
        h = win.height() if win.height() > 1 else self.height()
        return w, h, TOP_INSET, max(0, h - TOP_INSET - BOTTOM_INSET)

    def _layout(self):
        w, h, top, usable_h = self._usable()
        self.setFixedSize(w, h)
        cover = min(w - 40, 300)
        cx = (w - cover) // 2
        cy = top + 16
        self._cover.setFixedSize(cover, cover)
        self._cover.move(cx, cy)
        self._cover.show()
        # controls row: bottom edge inside the usable area
        sizes = {k: b.width() for k, b in self.ctrl.items()}
        row_h = max(sizes.values())
        row_y = top + usable_h - 10 - row_h
        total = sum(sizes.values())
        gap = max(8.0, (w - 32 - total) / 4.0)
        x = 16.0
        for kind in ("queue", "prev", "play", "next", "more"):
            b = self.ctrl[kind]
            b.move(int(round(x)), int(row_y + (row_h - sizes[kind]) / 2))
            b.show()
            x += sizes[kind] + gap
        # seek above the controls
        seek_h = 36
        self._seek.setGeometry(16, int(row_y - 14 - seek_h), w - 32, seek_h)
        self._seek.show()
        self._cover_y = cy
        self._cover_size = cover

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout()

    # ---- content -------------------------------------------------------------
    def set_track(self, t: dict):
        self._track = t
        title = t.get("title", "")
        self._cover.set_template(t.get("artwork_template", ""), t.get("album") or title)
        art = t.get("art_path", "")
        p = local_art(art, 512) if art else None
        if p and image_for(p) is not None:
            self._cover._img = image_for(p)
        self._bg_small = None               # recompute the blurred background
        self._seek.set_times(t.get("position_ms", 0), t.get("duration_ms", 0))
        play = self.ctrl["play"]
        play._kind = "pause" if t.get("playing") else "play"
        play.redraw()
        play.content_changed()
        self.redraw()
        self.content_changed()

    def _tick(self):
        if self._track.get("playing") and self._track.get("duration_ms"):
            self._track["position_ms"] = min(self._track["duration_ms"],
                                              self._track.get("position_ms", 0) + 1000)
            self._seek.set_times(self._track["position_ms"], self._track["duration_ms"])

    def _open_options(self):
        host = self.window()
        self._options = OptionsMenu(host, self._track)
        self._options.show()
        self._options.raise_()

    # ---- drawing -------------------------------------------------------------
    def _background(self, p: QPainter, w: float, h: float):
        img = self._cover._img
        if img is not None and not img.isNull():
            if self._bg_small is None:
                self._bg_small = img.scaled(24, 42, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawImage(QRectF(0, 0, w, h), self._bg_small)      # the "blur": tiny -> full
            p.fillRect(QRectF(0, 0, w, h), QColor(0, 0, 0, 175))   # dark veil for legibility
        else:
            c1, c2 = cover_colors(self._track.get("album") or self._track.get("title") or "")
            g = QLinearGradient(0, 0, w, h)
            g.setColorAt(0.0, QColor(c2).darker(200))
            g.setColorAt(1.0, QColor(0, 0, 0))
            p.fillRect(QRectF(0, 0, w, h), g)

    def draw(self, p: QPainter):
        w, h = float(self.width()), float(self.height())
        self._background(p, w, h)
        # cover shadow (one offset rect) — the cover itself is a child widget
        cs, cx, cy = self._cover_size, self._cover.x(), self._cover.y()
        p.fillRect(QRectF(cx + 6, cy + 8, cs, cs), QColor(0, 0, 0, 130))
        # texts centered under the cover, one line each with ellipsis
        ty = cy + cs + 18
        p.setPen(QColor("white"))
        p.setFont(ztos._font(ztos.FONT_LIGHT, 30))
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(16, ty, w - 32, 40), Qt.AlignHCenter,
                   fm.elidedText(self._track.get("title", ""), Qt.ElideRight, w - 32))
        p.setPen(QColor(255, 255, 255, 170))
        p.setFont(ztos._font(ztos.FONT_REGULAR, 16))
        fm2 = QFontMetricsF(p.font())
        sub = f"{self._track.get('artist', '')} — {self._track.get('album', '')}".strip(" —")
        p.drawText(QRectF(16, ty + 42, w - 32, 24), Qt.AlignHCenter,
                   fm2.elidedText(sub, Qt.ElideRight, w - 32))


class OptionsMenu(ztos.Entry):
    """The options menu: dark ztOS-style panel over the window, rows >= 48px,
    icon + label + optional sublabel. Only real, working entries."""

    ROW_H = 52

    def __init__(self, host, track: dict):
        super().__init__("", "")
        self._host = host
        self._track = track
        t = backend.now_playing()
        items = self._items(t)
        h = 12 + len(items) * self.ROW_H + 8
        self.setParent(host)
        self.setFixedHeight(h)                    # Entry fixes 45px otherwise
        bottom = host.height() - BOTTOM_INSET - 8
        self.setGeometry(20, max(20, bottom - h), host.width() - 40, h)
        self._items = items
        self._row_hit = [self.ROW_H] * len(items)

    def _items(self, t):
        sid = self._song_id(t)
        fav = bool(t.get("favorite"))
        items = [
            ("star", "Rimuovi dai preferiti" if fav else "Aggiungi ai preferiti", "",
             lambda: backend.write("unfavorite" if fav else "favorite", sid)),
            ("album", "Vai all'album", t.get("album", ""),
             lambda: self._go("albums", t.get("album", ""), "album")),
            ("artist", "Vai all'artista", t.get("artist", ""),
             lambda: self._go("artists", t.get("artist", ""), "artist")),
            ("shuffle", "shuffle", "on" if t.get("shuffle") else "off",
             lambda: backend.set_shuffle(not t.get("shuffle"))),
            ("repeat", "repeat", t.get("repeat", "none"),
             lambda: backend.set_repeat(_next_repeat(t.get("repeat", "none")))),
        ]
        return items

    def _song_id(self, t):
        items, pos = backend.queue_items()
        if items and 0 <= pos < len(items):
            return items[pos].get("id") or ""
        return (self._track.get("track_id") or "")

    def _go(self, view, name, kind):
        for row in backend.browse(view):
            if rtitle(row) == name:
                from hub import DetailPage
                ztos.App.current.push(DetailPage(row.get("pageKind", kind), row.get("id", "")))
                return

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        p.fillRect(r, QColor(24, 24, 24, 242))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawRect(r)
        y = 12.0
        for icon, label, sub, _cb in self._items:
            _draw_menu_icon(p, icon, 26, y + self.ROW_H / 2.0)
            p.setPen(QColor("white"))
            p.setFont(ztos._font(ztos.FONT_REGULAR, 16))
            p.drawText(QPointF(44, y + 22), label)
            if sub:
                p.setPen(QColor(255, 255, 255, 140))
                p.setFont(ztos._font(ztos.FONT_REGULAR, 12.5))
                p.drawText(QPointF(44, y + 40), sub)
            y += self.ROW_H

    def mousePressEvent(self, event):
        pass

    def mouseReleaseEvent(self, event):
        y = event.position().y() - 12.0
        i = int(y // self.ROW_H)
        self.close()
        self.deleteLater()
        if 0 <= i < len(self._items):
            ztos.haptic("tap")
            self._items[i][3]()


def _next_repeat(cur):
    order = ["none", "one", "all"]
    return order[(order.index(cur) + 1) % len(order)] if cur in order else "all"


def _draw_menu_icon(p: QPainter, name: str, size: float, cy: float):
    p.save()
    p.translate(12 + size / 2, cy)
    p.setPen(QPen(QColor("white"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    s = size / 2
    if name == "star":
        path = QPainterPath()
        import math
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = s if i % 2 == 0 else s * 0.45
            (path.lineTo if i else path.moveTo)(math.cos(ang) * r, math.sin(ang) * r)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "album":
        p.drawRect(QRectF(-s * 0.8, -s * 0.8, s * 1.6, s * 1.6))
        p.drawEllipse(QPointF(0, 0), s * 0.35, s * 0.35)
    elif name == "artist":
        p.drawEllipse(QPointF(0, -s * 0.45), s * 0.35, s * 0.35)
        p.drawArc(QRectF(-s * 0.7, -s * 0.1, s * 1.4, s * 1.4), 0, 180 * 16)
    elif name == "shuffle":
        p.drawLine(QPointF(-s, -s * 0.4), QPointF(s, -s * 0.4))
        p.drawLine(QPointF(-s, s * 0.4), QPointF(s, s * 0.4))
    elif name == "repeat":
        p.drawArc(QRectF(-s * 0.8, -s * 0.8, s * 1.6, s * 1.6), 30 * 16, 300 * 16)
    p.restore()


class NowPlaying(ztos.Page):
    """The Now Playing page: one PlayerView filling it. Back pops it."""

    def __init__(self, app):
        super().__init__("", header=False)
        self.list.setContentsMargins(0, 0, 0, 0)
        self.view = PlayerView(app)
        self.add(self.view)
        backend.snapshot_changed.connect(self._refresh)

    def shown(self):
        self._refresh()

    def _refresh(self):
        t = backend.now_playing()
        t["favorite"] = self._favorite_flag(t)
        self.view.set_track(t)

    def _favorite_flag(self, t):
        """Favorite state of the current track, from the cached songs rows."""
        with backend._lock:
            rows = backend._rows.get("songs")
        if rows:
            for r in rows:
                if r.get("title") == t.get("title") and r.get("artist") == t.get("artist"):
                    return bool(r.get("favorite"))
        return False


def _queue_page():
    from screens import QueuePage
    return QueuePage()
