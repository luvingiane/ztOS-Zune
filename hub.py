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
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QPainter

from art import Artwork, prewarm
from client import backend, rtitle, SORTS, SORT_LABELS
from widgets import Row, Cover, LIST_X, fmt_ms, ROW_H

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
    """A collection page of rows; `view` is the slipmatd View name.
    Long lists are built in chunks (only the visible + buffer rows exist as
    widgets), so filling a 500-song list never blocks the GUI thread."""

    view = ""
    CHUNK = 40

    def __init__(self, title: str):
        super().__init__(title, header=False)
        self.list.setContentsMargins(LIST_X, 0, 16, 24)
        self._all_items = []
        self._built = 0
        self._extend_timer = None

    def shown(self):
        # show the page at once (title/loading), fill when the data arrives:
        # no heavy work on the tap path (reactivity budget < 150 ms)
        self.clear()
        sort, reverse = get_sort(self.view)
        if backend.live:
            self.add(Notice("loading…"))
        backend.browse_async(self.view, sort, reverse, cb=self._on_rows)

    def _on_rows(self, rows):
        if not self.isVisible():
            return
        self.clear()
        if not backend.live:
            self.add(Notice(backend.demo_notice or "demo data"))
        elif not rows:
            self.add(Notice(f"error: {backend.last_error}" if backend.last_error else "empty"))
        self._all_items = rows
        self._items = rows            # all items (SongsPage plays from this list)
        self._built = 0
        from PySide6.QtCore import QTimer
        self._extend_timer = QTimer(self, interval=150)
        self._extend_timer.timeout.connect(self._maybe_extend)
        self._extend_timer.start()
        self._build_chunk()
        prewarm(rows[:60], GRID_ART)
        QTimer.singleShot(6000, self._refresh_stale)

    def _refresh_stale(self):
        """Signed playlist URLs expire: if their fetch failed (art.stale),
        ask the daemon once for fresh rows/URLs."""
        import art
        if not self.isVisible():
            return
        mine = {it.get("artworkTemplate", "") for it in self._all_items if it.get("artworkTemplate")}
        hit = art.stale & mine
        if hit:
            art.stale -= hit
            sort, reverse = get_sort(self.view)
            backend.browse_async(self.view, sort, reverse, cb=self._on_rows)

    def _build_chunk(self):
        end = min(len(self._all_items), self._built + self.CHUNK)
        for i in range(self._built, end):
            self.add(self.make_row(self._all_items[i], i))
        self._built = end

    def _maybe_extend(self):
        view_h = self.viewport.height() if self.viewport.height() > 1 else 500
        if self._scroll + view_h * 2 > self._built * ROW_H and self._built < len(self._all_items):
            self._build_chunk()
            prewarm(self._all_items[self._built:self._built + 60], GRID_ART)

    def make_row(self, item, index):
        raise NotImplementedError

    def fill(self):
        self.shown()


class ArtistsPage(ListPage):
    view = "artists"

    def __init__(self, app):
        super().__init__("artists")
        self._app = app

    def make_row(self, a, index):
        return Row(rtitle(a), a.get("subtitle", ""),
                   art=a.get("artworkTemplate", ""),
                   on_tap=lambda a=a: self._app.push(DetailPage(a.get("pageKind", "artist"),
                                                                a.get("id", ""), rtitle(a))))


class SongsPage(ListPage):
    view = "songs"

    def __init__(self, app):
        super().__init__("songs")
        self._app = app
        self._items = []

    def make_row(self, s, i):
        return Row(rtitle(s), s.get("subtitle", ""), s.get("durationMs", 0),
                   art=s.get("artworkTemplate", ""),
                   on_tap=lambda i=i: self._play(i),
                   on_hold=lambda s=s: self._menu(s))

    def _play(self, i):
        import player
        ztos.haptic("tap")
        sent, reason = backend.play_list(self._items, i)
        if not sent:
            ztos.notify("cannot play", reason or "slipmatd not ready")
            return
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

    def make_row(self, pl, index):
        return Row(rtitle(pl), pl.get("subtitle", ""),
                   art=pl.get("artworkTemplate", ""),
                   on_tap=lambda pl=pl: self._app.push(DetailPage(pl.get("pageKind", "playlist"),
                                                                  pl.get("id", ""), rtitle(pl))))


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

    def make_row(self, al, index):
        return AlbumGrid([al], on_tap=lambda al=al: None)   # albums use the grid below

    def _on_rows(self, rows):
        if not self.isVisible():
            return
        self.clear()
        if not backend.live:
            self.add(Notice(backend.demo_notice or "demo data"))
        self._grid = AlbumGrid(rows, on_tap=lambda al: self._app.push(
            DetailPage(al.get("pageKind", "album"), al.get("id", ""), rtitle(al))))
        self.add(self._grid)
        self._grid.build_cells()
        prewarm(rows, GRID_ART)


class DetailPage(ztos.Page):
    """Album / artist / playlist page, metro style: compact header (real cover
    140px left, name in light type, artist/curator, track count + total time)
    + one action row (play / shuffle / queue / more) like the original's
    detail_page.rs header buttons, then the track rows with thumbs."""

    def __init__(self, kind: str, id_: str, title: str = "…"):
        super().__init__(title)
        self._kind, self._id = kind, id_
        self._title_hint = title
        self._entries = []
        self._header = {}

    def shown(self):
        # page visible immediately with its title; the open() round trip is async
        self.clear()
        self.title = self._title_hint
        if backend.live:
            self.add(Notice("loading…"))
        backend.open_page_async(self._kind, self._id, cb=self._on_page)

    def _on_page(self, header, entries):
        if not self.isVisible() or header is None:
            return
        self.clear()
        self.title = rtitle(header)
        if not backend.live and not entries:
            self.add(Notice(backend.demo_notice or "demo data"))
        self._entries = entries
        self._header = header
        if "playlist" in (self._kind or "") and not header.get("artworkTemplate") and entries:
            import art as _art
            paths = [_art.local_art(e.get("artworkTemplate", ""), 300) for e in entries[:4]]
            paths = [p for p in paths if p]
            if len(paths) == len([e for e in entries[:4] if e.get("artworkTemplate")]):
                mosaic = _art.mosaic_image(paths, 300)
                if mosaic is not None:
                    self._mosaic = mosaic
        self._header_block(header)
        np = backend.now_playing()
        for i, e in enumerate(entries):
            cur = (np.get("title") == rtitle(e) and np.get("artist") == e.get("artist", ""))
            self.add(Row(rtitle(e), e.get("subtitle", ""), e.get("durationMs", 0),
                         art=e.get("artworkTemplate", ""), accent=cur,
                         on_tap=lambda i=i: self._play_from(i)))
        prewarm([header] + entries, GRID_ART)

    def _play_from(self, i):
        """Tap a track row: play from that row, the rest of the list in queue
        (play {ids, index} like the original: track_row.rs / link.rs)."""
        import player
        ztos.haptic("tap")
        sent, reason = backend.play_list(self._entries, i)
        if not sent:
            ztos.notify("cannot play", reason or "slipmatd not ready")
            return
        ztos.App.current.push(player.NowPlaying(ztos.App.current))

    def _header_block(self, header):
        from PySide6.QtWidgets import QWidget, QHBoxLayout
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(14)
        cover = Artwork(140, rtitle(header), header.get("artworkTemplate", ""), 300)
        if getattr(self, "_mosaic", None) is not None:
            cover._img = self._mosaic
        lay.addWidget(cover)
        texts = QWidget()
        from PySide6.QtWidgets import QVBoxLayout, QLabel
        tv = QVBoxLayout(texts)
        tv.setContentsMargins(0, 0, 0, 0)
        name = QLabel(rtitle(header))
        name.setFont(ztos._font(ztos.FONT_LIGHT, 30))
        name.setStyleSheet("color: white;")
        sub = QLabel(header.get("subtitle", ""))
        sub.setFont(ztos._font(ztos.FONT_REGULAR, 15))
        sub.setStyleSheet("color: rgba(255,255,255,0.6);")
        n = len(self._entries)
        total = sum(e.get("durationMs", 0) for e in self._entries)
        meta = QLabel(f"{n} tracks · {fmt_ms(total)}" if n else "")
        meta.setFont(ztos._font(ztos.FONT_REGULAR, 13))
        meta.setStyleSheet("color: rgba(255,255,255,0.45);")
        tv.addWidget(name)
        tv.addWidget(sub)
        tv.addWidget(meta)
        tv.addStretch(1)
        lay.addWidget(texts, 1)
        self.add(row)
        # action row: play / shuffle / queue / more (detail_page.rs header buttons)
        import player as _player
        actions = self.round_buttons(
            _player.CtrlButton("play", self._play_all, 52),
            _player.CtrlButton("shuffle", self._play_shuffled, 52),
            _player.CtrlButton("queue", self._enqueue_all, 52),
            _player.CtrlButton("more", self._more_menu, 52))
        self.space(4)

    def _play_all(self):
        sent, reason = backend.play_list(self._entries, 0)
        if not sent:
            ztos.notify("cannot play", reason or "slipmatd not ready")

    def _play_shuffled(self):
        ids = [e.get("catalogId") for e in self._entries if e.get("catalogId")]
        if ids and backend.live:
            backend._send(backend._client.play, ids, 0, "shuffled")

    def _enqueue_all(self):
        ids = [e.get("catalogId") for e in self._entries if e.get("catalogId")]
        if ids:
            backend.enqueue(ids)

    def _more_menu(self):
        in_lib = bool(self._header.get("library"))
        hid = self._header.get("id", "")
        ztos.menu(self, [
            ("add to queue", self._enqueue_all),
            ("remove from library" if in_lib else "add to library",
             lambda: backend.write("removeFromLibrary" if in_lib else "addToLibrary", hid)),
        ])


class MusicHub(ztos.Pivot):
    """artists | albums | songs | playlists | settings. Back from here closes
    the app (it is the only page on the stack)."""

    def __init__(self, app):
        import player
        self._app = app
        self._pages = [PlaylistsPage(app), SongsPage(app), AlbumsPage(app),
                       ArtistsPage(app), screens.SettingsPage()]
        super().__init__(self._pages)
        self.turned.connect(self._sort_label)
        import icons as _icons  # noqa: F401  (glyphs live only in icons.py)
        self._sort_btn = player.CtrlButton("sort", self._sort_menu, 52, label="sort")
        self.bar(self._sort_btn,
                 player.CtrlButton("search", lambda: app.push(screens.SearchPage()), 52, label="search"),
                 player.CtrlButton("queue", lambda: app.push(screens.QueuePage()), 52, label="queue"),
                 player.CtrlButton("play", lambda: app.push(player.NowPlaying(app)), 52, label="now playing"))
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
