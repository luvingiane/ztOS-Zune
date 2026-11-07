"""The music collection hub: a ztos.Pivot with artists / albums / songs /
playlists (DESIGN.md §4.2, §4.5), fed by client.backend (slipmatd or demo).
"""
import ztos
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter

from client import backend
from widgets import Row, Cover, LIST_X, draw_cover


class ListPage(ztos.Page):
    """A collection page of rows; `fill` rebuilds it (called on shown())."""

    def __init__(self, title: str):
        super().__init__(title, header=False)
        self.list.setContentsMargins(LIST_X, 0, 16, 24)
        self._fill = None

    def set_fill(self, fn):
        self._fill = fn

    def shown(self):
        if self._fill:
            self._fill()


class ArtistsPage(ListPage):
    def __init__(self, app):
        super().__init__("artists")
        self._app = app
        self.set_fill(self.fill)

    def fill(self):
        self.clear()
        for a in backend.browse("artists"):
            self.add(Row(a.get("name", ""), a.get("subtitle", ""),
                         on_tap=lambda a=a: self._app.push(ArtistPage(a))))


class ArtistPage(ztos.Page):
    def __init__(self, artist: dict):
        super().__init__(artist.get("name", "artist"))
        self.text(artist.get("subtitle", ""))
        for al in backend.browse("albums"):
            if al.get("artist") == artist.get("name"):
                self.add(Row(al.get("name", ""), al.get("subtitle", "")))


class SongsPage(ListPage):
    def __init__(self, app):
        super().__init__("songs")
        self._app = app
        self.set_fill(self.fill)

    def fill(self):
        self.clear()
        for s in backend.browse("songs"):
            self.add(Row(s.get("title", ""), s.get("subtitle", ""), s.get("duration_ms", 0),
                         on_tap=lambda s=s: self._play(s),
                         on_hold=lambda s=s: self._menu(s)))

    def _play(self, s):
        import screens
        ztos.haptic("tap")
        backend.play_ids([s.get("id", "")], 0)
        self._app.push(screens.NowPlaying(self._app))

    def _menu(self, s):
        ztos.menu(self, [("enqueue", lambda s=s: backend.enqueue([s.get("id", "")])),
                         ("enqueue next", lambda s=s: backend.enqueue([s.get("id", "")], next_=True))])


class PlaylistsPage(ListPage):
    def __init__(self, app):
        super().__init__("playlists")
        self._app = app
        self.set_fill(self.fill)

    def fill(self):
        self.clear()
        for pl in backend.browse("playlists"):
            self.add(Row(pl.get("name", ""), pl.get("subtitle", ""),
                         on_tap=lambda pl=pl: self._app.push(PlaylistPage(pl))))


class PlaylistPage(ztos.Page):
    def __init__(self, pl: dict):
        super().__init__(pl.get("name", "playlist"))
        for t in pl.get("tracks", []):
            self.add(Row(t.get("title", ""), f"{t.get('artist', '')} — {t.get('album', '')}"))


class AlbumGrid(ztos.Entry):
    """The albums grid (A1): square gradient covers, name under each; 3 columns."""

    CELL_W, CELL_H = 108, 138

    def __init__(self, albums, on_tap):
        super().__init__("", "", on_tap=None)
        self._albums = albums
        self._on_tap = on_tap
        rows = (len(albums) + 2) // 3
        self.setFixedHeight(rows * self.CELL_H)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        for i, al in enumerate(self._albums):
            col, row = i % 3, i // 3
            x, y = col * self.CELL_W, row * self.CELL_H
            draw_cover(p, QRectF(x + 2, y + 2, self.CELL_W - 4, self.CELL_W - 4), al.get("name", ""))
            p.setPen(QColor("white"))
            p.setFont(ztos._font(ztos.FONT_REGULAR, 13))
            fm = QFontMetricsF(p.font())
            p.drawText(QPointF(x + 2, y + self.CELL_W + 4 + fm.ascent()),
                       fm.elidedText(al.get("name", ""), Qt.ElideRight, self.CELL_W - 4))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        i = int(event.position().y() // self.CELL_H) * 3 + int(event.position().x() // self.CELL_W)
        if 0 <= i < len(self._albums):
            self._on_tap(self._albums[i])


class AlbumsPage(ListPage):
    def __init__(self, app):
        super().__init__("albums")
        self._app = app
        self.set_fill(self.fill)

    def fill(self):
        self.clear()
        self.add(AlbumGrid(backend.browse("albums"),
                           on_tap=lambda al: self._app.push(AlbumPage(al))))


class AlbumPage(ztos.Page):
    def __init__(self, album: dict):
        super().__init__(album.get("name", "album"))
        self.space(8)
        self.add(Cover(180, album.get("name", "")))
        self.text(album.get("subtitle", ""))
        for s in backend.browse("songs"):
            if s.get("album") == album.get("name"):
                self.add(Row(f"{s.get('track_number', 0)}. {s.get('title', '')}",
                             s.get("artist", ""), s.get("duration_ms", 0)))


class MusicHub(ztos.Pivot):
    """artists | albums | songs | playlists, swiping side to side (DESIGN §4.2)."""

    def __init__(self, app):
        import screens
        self._app = app
        super().__init__([ArtistsPage(app), AlbumsPage(app), SongsPage(app), PlaylistsPage(app)])
        self.bar(ztos.RoundButton("search", "search", lambda: app.push(screens.SearchPage())),
                 ztos.RoundButton("more", "queue", lambda: app.push(screens.QueuePage())))
