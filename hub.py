"""The music hub: a ztos.Pivot with artists / albums / songs / playlists /
settings (the app opens directly here — stage 3 navigation, see STATO.md).

All rows come from client.backend: slipmatd rows (entry_to_dict: "title" is
the main text, "subtitle" the secondary, "artworkTemplate" the cover) when the
daemon is ready, demo data otherwise with a visible notice row. Each view has
its own sort (SortBy::for_view, slipmat-core/src/sort.rs), chosen from the
app bar's sort button, direction included, remembered between sessions.
"""
import ztos
import screens
import player
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter

from art import Artwork, prewarm
from client import backend, rtitle, SORTS, SORT_LABELS
from widgets import Row, Cover, LIST_X, fmt_ms

GRID_ART = 300       # artwork size requested for grid cells (cell is 104 logical)


class Notice(ztos.Entry):
    """A grey status line at the top of a list (demo mode, loading, errors)."""

    def __init__(self, text: str):
        super().__init__("", "")
        self._text = text
        self.setFixedHeight(30)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(QColor(255, 255, 255, 110))
        p.setFont(ztos._font(ztos.FONT_REGULAR, 13))
        fm = QFontMetricsF(p.font())
        p.drawText(QPointF(0, (self.height() + fm.ascent() - fm.descent()) / 2.0),
                   fm.elidedText(self._text, Qt.ElideRight, self.width()))


def _store():
    return ztos.store("zunehd")


def get_sort(view: str):
    """(sort, reverse) remembered for this view, validated against SortBy::for_view."""
    saved = _store().get("sort", {}).get(view, {})
    sort = saved.get("sort", "title")
    if sort not in SORTS[view]:
        sort = SORTS[view][0]
    return sort, bool(saved.get("reverse", False))


def set_sort(view: str, sort: str, reverse: bool):
    st = _store()
    sorts = dict(st.get("sort", {}))
    sorts[view] = {"sort": sort, "reverse": reverse}
    st["sort"] = sorts
    st.save()


class ListPage(ztos.Page):
    """A collection page of rows; `view` is the slipmatd View name."""

    view = ""

    def __init__(self, title: str):
        super().__init__(title, header=False)
        self.list.setContentsMargins(LIST_X, 0, 16, 24)

    def shown(self):
        self.fill()

    def fill(self):
        self.clear()
        sort, reverse = get_sort(self.view)
        rows = backend.browse(self.view, sort, reverse)
        if not backend.live:
            self.add(Notice(backend.demo_notice or "demo data"))
        elif not rows:
            self.add(Notice("loading…" if not backend.last_error else f"error: {backend.last_error}"))
        self.build(rows)
        prewarm(rows, GRID_ART)

    def build(self, rows):
        raise NotImplementedError


class ArtistsPage(ListPage):
    view = "artists"

    def __init__(self, app):
        super().__init__("artists")
        self._app = app

    def build(self, rows):
        for a in rows:
            self.add(Row(rtitle(a), a.get("subtitle", ""),
                         on_tap=lambda a=a: self._app.push(DetailPage(a.get("pageKind", "artist"),
                                                                     a.get("id", "")))))


class SongsPage(ListPage):
    view = "songs"

    def __init__(self, app):
        super().__init__("songs")
        self._app = app

    def build(self, rows):
        import player
        for s in rows:
            self.add(Row(rtitle(s), s.get("subtitle", ""), s.get("durationMs", 0),
                         on_tap=lambda s=s: self._play(s),
                         on_hold=lambda s=s: self._menu(s)))

    def _play(self, s):
        import player
        ztos.haptic("tap")
        ids = [s.get("catalogId") or s.get("id", "")]
        backend.play_ids(ids, 0)
        self._app.push(player.NowPlaying(self._app))

    def _menu(self, s):
        sid = s.get("catalogId") or s.get("id", "")
        items = [("play next", lambda: backend.enqueue([sid], next_=True)),
                 ("add to queue", lambda: backend.enqueue([sid]))]
        if s.get("inLibrary") or s.get("libraryId"):
            items.append(("remove from library", lambda: backend.write("removeFromLibrary", s.get("libraryId") or sid)))
            items.append(("unfavorite" if s.get("favorite") else "favorite",
                          lambda: backend.write("unfavorite" if s.get("favorite") else "favorite", sid)))
        else:
            items.append(("add to library", lambda: backend.write("addToLibrary", sid)))
        ztos.menu(self, items)


class PlaylistsPage(ListPage):
    view = "playlists"

    def __init__(self, app):
        super().__init__("playlists")
        self._app = app

    def build(self, rows):
        for pl in rows:
            self.add(Row(rtitle(pl), pl.get("subtitle", ""),
                         on_tap=lambda pl=pl: self._app.push(DetailPage(pl.get("pageKind", "playlist"),
                                                                        pl.get("id", "")))))


class AlbumGrid(ztos.Entry):
    """The albums grid (A1): real covers when cached, gradient until then."""

    CELL_W, CELL_H = 108, 140

    def __init__(self, albums, on_tap):
        super().__init__("", "", on_tap=None)
        self._albums = albums
        self._on_tap = on_tap
        self._cells = []
        rows = (len(albums) + 2) // 3
        self.setFixedHeight(rows * self.CELL_H)

    def build_cells(self):
        for i, al in enumerate(self._albums):
            col, row = i % 3, i // 3
            w = Artwork(self.CELL_W - 4, rtitle(al), al.get("artworkTemplate", ""), GRID_ART)
            w.setParent(self)
            w.move(col * self.CELL_W + 2, row * self.CELL_H + 2)
            w.show()
            self._cells.append(w)

    def draw(self, p: QPainter):
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        for i, al in enumerate(self._albums):
            col, row = i % 3, i // 3
            x, y = col * self.CELL_W, row * self.CELL_H
            p.setPen(QColor("white"))
            p.setFont(ztos._font(ztos.FONT_REGULAR, 13))
            fm = QFontMetricsF(p.font())
            p.drawText(QPointF(x + 2, y + self.CELL_W + 2 + fm.ascent()),
                       fm.elidedText(rtitle(al), Qt.ElideRight, self.CELL_W - 4))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        i = int(event.position().y() // self.CELL_H) * 3 + int(event.position().x() // self.CELL_W)
        if 0 <= i < len(self._albums):
            self._on_tap(self._albums[i])


class AlbumsPage(ListPage):
    view = "albums"

    def __init__(self, app):
        super().__init__("albums")
        self._app = app
        self._grid = None

    def build(self, rows):
        self._grid = AlbumGrid(rows, on_tap=lambda al: self._app.push(
            DetailPage(al.get("pageKind", "album"), al.get("id", ""))))
        self.add(self._grid)
        self._grid.build_cells()


class DetailPage(ztos.Page):
    """An album / artist / playlist page: header cover + rows (`open` req)."""

    def __init__(self, kind: str, id_: str):
        super().__init__("…")
        self._kind, self._id = kind, id_

    def shown(self):
        self.clear()
        header, entries = backend.open_page(self._kind, self._id)
        if header is None:
            self.add(Notice("loading…" if backend.live else (backend.demo_notice or "demo data")))
            return
        self.title = rtitle(header)
        if not backend.live and not entries:
            self.add(Notice(backend.demo_notice or "demo data"))
        tpl = header.get("artworkTemplate", "")
        if tpl or header.get("artPath"):
            cover = Artwork(120, rtitle(header), tpl, 300)
            if header.get("artPath"):
                from art import local_art, image_for
                p = local_art(header["artPath"], 512)
                if p:
                    cover._img = image_for(p)
            self.space(8)
            self.add(cover)
        sub = header.get("subtitle", "")
        if sub:
            self.add(Notice(sub))
        for e in entries:
            self.add(Row(rtitle(e), e.get("subtitle", ""), e.get("durationMs", 0)))
        prewarm(entries, GRID_ART)


class MusicHub(ztos.Pivot):
    """artists | albums | songs | playlists | settings. Back from here closes
    the app (it is the only page on the stack)."""

    def __init__(self, app):
        import player
        self._app = app
        self._pages = [ArtistsPage(app), AlbumsPage(app), SongsPage(app),
                       PlaylistsPage(app), screens.SettingsPage()]
        super().__init__(self._pages)
        self.turned.connect(self._sort_label)
        self._sort_btn = ztos.RoundButton("more", "sort", self._sort_menu)
        self.bar(self._sort_btn,
                 ztos.RoundButton("search", "search", lambda: app.push(screens.SearchPage())),
                 ztos.RoundButton("more", "queue", lambda: app.push(screens.QueuePage())),
                 ztos.RoundButton("play", "now playing", lambda: app.push(player.NowPlaying(app))))
        backend.changed.connect(self._refill)
        self._sort_label(0)

    def _view(self):
        return self._pages[self.index].view if hasattr(self._pages[self.index], "view") else ""

    def _refill(self):
        page = self.current()
        if hasattr(page, "fill"):
            page.fill()

    def _sort_label(self, _i):
        view = self._view()
        if view:
            sort, reverse = get_sort(view)
            arrow = "↓" if ((sort in ("year", "added", "updated")) != reverse) else "↑"
            self._sort_btn.set_label(f"{SORT_LABELS.get(sort, sort)} {arrow}")

    def _sort_menu(self):
        view = self._view()
        if not view:
            return
        sort, reverse = get_sort(view)
        items = [(f"{SORT_LABELS.get(s, s)}{'  ✓' if s == sort else ''}",
                  (lambda s=s: self._choose_sort(view, s))) for s in SORTS[view]]
        items.append((f"direction: {'descending' if ((sort in ('year', 'added', 'updated')) != reverse) else 'ascending'}"
                      f"{'  ✓' if reverse else ''}",
                      lambda: self._choose_sort(view, sort, not reverse)))
        ztos.menu(self._sort_btn, items)

    def _choose_sort(self, view, sort, reverse=None):
        _, cur_rev = get_sort(view)
        if reverse is None:
            reverse = cur_rev
        set_sort(view, sort, reverse)
        self._sort_label(self.index)
        self._refill()
