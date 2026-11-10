"""The music hub: a ztos.Pivot with artists / albums / songs / playlists /
settings (the app opens directly here — stage 3 navigation, see STATO.md).

All rows come from client.backend: slipmatd rows (entry_to_dict: "title" is
the main text, "subtitle" the secondary, "artworkTemplate" the cover) when the
daemon is ready, demo data otherwise with a visible notice row. Each view has
its own sort (SortBy::for_view, slipmat-core/src/sort.rs), chosen from the
app bar's sort button, direction included, remembered between sessions.
"""
import ztos
import icons
import screens
import player
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QPainter

from art import Artwork, prewarm
from client import backend, rtitle, is_available, SORTS, SORT_LABELS
from widgets import Row, Cover, CircleButton, RowWarmer, LIST_X, fmt_ms, ROW_H

GRID_ART = 300       # artwork size requested for grid cells (cell is 104 logical)


def song_menu(anchor, s):
    """The hold menu of a song row (songs list, playlist/album/artist pages,
    search): play next, queue, favorite, library. `s` is an entry_to_dict row."""
    sid = s.get("catalogId") or s.get("id", "")
    if not is_available(s):
        ztos.notify("unavailable", "this track cannot be streamed")
    items = []
    if is_available(s):
        items += [("play next", lambda: backend.enqueue([sid], next_=True)),
                  ("add to queue", lambda: backend.enqueue([sid]))]
    if s.get("inLibrary") or s.get("libraryId"):
        items.append(("remove from library", lambda: backend.write("removeFromLibrary", s.get("libraryId") or sid)))
        items.append(("unfavorite" if s.get("favorite") else "favorite",
                      lambda: backend.write("unfavorite" if s.get("favorite") else "favorite", sid)))
    elif sid:
        items.append(("add to library", lambda: backend.write("addToLibrary", sid)))
    if items:
        ztos.menu(anchor, items)


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
        self._warmer = RowWarmer(self)

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
        self._warmer.start()
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
        if self._built >= len(self._all_items):
            if self._extend_timer is not None:
                self._extend_timer.stop()          # everything built: no more 150 ms wake-ups
            return
        if self._scroll + view_h * 2 > self._built * ROW_H:
            self._build_chunk()
            self._warmer.start()
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
                   art=s.get("artworkTemplate", ""), available=is_available(s),
                   on_tap=lambda i=i: self._play(i),
                   on_hold=lambda s=s: self._menu(s))

    def _play(self, i):
        import player
        ztos.haptic("tap")
        sent, reason = backend.play_list(self._items, i)
        if not sent:
            ztos.notify("cannot play", reason or "slipmatd not ready")
            return
        if reason:
            ztos.notify("unavailable", reason)
        self._app.push(player.NowPlaying(self._app))

    def _menu(self, s):
        song_menu(self, s)


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
            w.setAttribute(Qt.WA_TransparentForMouseEvents)   # the tap must reach the grid, not the cover
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


class ArtistHero(ztos.Entry):
    """Top of an artist page: the artist picture cropped to fill the width,
    darkened toward the bottom, name large over it (like the Apple Music
    profile: picture, name, then play/shuffle). The picture arrives async."""

    H = 250

    def __init__(self, name: str, genres: str, template: str):
        super().__init__("", "")
        self._name, self._genres, self._t = name, genres, template or ""
        self._img = None
        self.setFixedHeight(self.H)
        if self._t:
            import art as art_mod
            p = art_mod.local_art(self._t, 512)
            if p:
                self._img = art_mod.image_for(p)
            else:
                art_mod.add_listener(self._on_art, self._t)
                art_mod._fetcher.add(self._t, 512)

    def _on_art(self, template, path, ok):
        if ok and template == self._t:
            import art as art_mod
            img = art_mod.image_for(path)
            if img is not None and not img.isNull():
                self._img = img
                self.redraw()
                self.content_changed()

    def draw(self, p: QPainter):
        from PySide6.QtGui import QLinearGradient
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        w, h = float(self.width()), float(self.height())
        if self._img is not None and not self._img.isNull():
            s = max(w / self._img.width(), h / self._img.height())
            iw, ih = self._img.width() * s, self._img.height() * s
            p.drawImage(QRectF((w - iw) / 2, 0, iw, ih), self._img)      # top-anchored crop (faces)
        else:
            from widgets import draw_cover
            draw_cover(p, QRectF(0, 0, w, h), self._name)
        g = QLinearGradient(0, h * 0.45, 0, h)
        g.setColorAt(0.0, QColor(0, 0, 0, 0))
        g.setColorAt(1.0, QColor(0, 0, 0, 235))
        p.fillRect(QRectF(0, 0, w, h), g)
        p.setPen(QColor("white"))
        p.setFont(ztos._font(ztos.FONT_LIGHT, 38))
        fm = QFontMetricsF(p.font())
        p.drawText(QPointF(0, h - 30), fm.elidedText(self._name, Qt.ElideRight, w))
        if self._genres:
            p.setPen(QColor(255, 255, 255, 170))
            p.setFont(ztos._font(ztos.FONT_REGULAR, 14))
            p.drawText(QPointF(1, h - 9), self._genres)


def _split_discography(albums):
    """Albums vs singles/EPs (Apple titles them "X - Single" / "X - EP"),
    newest first; titles trimmed of that suffix for display."""
    full, small = [], []
    for a in albums:
        t = rtitle(a)
        a = dict(a)
        for suf in (" - Single", " - EP"):
            if t.endswith(suf):
                a["title"] = t[: -len(suf)]
                small.append(a)
                break
        else:
            full.append(a)
    key = lambda a: str(a.get("year") or "")
    return sorted(full, key=key, reverse=True), sorted(small, key=key, reverse=True)


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
        if "artist" in (self._kind or "").lower():
            self._artist_page(header, entries)
            return
        if "playlist" in (self._kind or "") and not header.get("artworkTemplate") and entries:
            import art as _art
            paths = [_art.local_art(e.get("artworkTemplate", ""), 300) for e in entries[:4]]
            paths = [p for p in paths if p]
            if len(paths) == len([e for e in entries[:4] if e.get("artworkTemplate")]):
                mosaic = _art.mosaic_image(paths, 300)
                if mosaic is not None:
                    self._mosaic = mosaic
        # the daemon's `open` returns SONGS for album/playlist pages but ALBUMS
        # for an artist page (verified on B 10/11): split by entry kind so an
        # album row opens its page instead of being "played" as a track
        songs = [e for e in entries if e.get("kind", "song") == "song"]
        others = [e for e in entries if e.get("kind", "song") != "song"]
        self._entries = songs
        self._header_block(header, n_others=len(others))
        np = backend.now_playing()
        if others:
            self.section("albums" if all(e.get("kind") == "album" for e in others) else "more")
            for e in others:
                self.add(Row(rtitle(e), e.get("subtitle", ""), art=e.get("artworkTemplate", ""),
                             on_tap=lambda e=e: ztos.App.current.push(
                                 DetailPage(e.get("pageKind", e.get("kind", "album")), e.get("id", ""), rtitle(e)))))
        if songs and others:
            self.section("songs")
        for i, e in enumerate(songs):
            cur = (np.get("title") == rtitle(e) and np.get("artist") == e.get("artist", ""))
            self.add(Row(rtitle(e), e.get("subtitle", ""), e.get("durationMs", 0),
                         art=e.get("artworkTemplate", ""), accent=cur,
                         available=is_available(e),
                         on_tap=lambda i=i: self._play_from(i),
                         on_hold=lambda e=e: song_menu(self, e)))
        prewarm([header] + entries, GRID_ART)

    # ---- artist profile ---------------------------------------------------------
    def _artist_page(self, header, entries):
        """Artist profile built from what the daemon can give: the artist
        picture + name, play/shuffle over the TOP SONGS (catalog search by the
        artist's name: Apple ranks by popularity), the latest release, the
        albums and the singles/EPs. For a library artist the full catalog
        discography is fetched too. (The daemon has no videos, playlists,
        radio or similar-artists endpoints.)"""
        name = rtitle(header)
        self.header.setVisible(False)            # the hero carries the name
        self._entries = []                       # top songs, filled async
        self._alb_widgets = []
        self.add(ArtistHero(name, header.get("subtitle", "") or header.get("genres", ""),
                            header.get("artworkTemplate", "")))
        self.space(6)
        self.round_buttons(
            CircleButton(icons.path("play"), on_tap=self._play_all),
            CircleButton(icons.path("shuffle"), on_tap=self._play_shuffled),
            CircleButton(icons.path("queue"), on_tap=self._enqueue_all),
            CircleButton(icons.path("more"), on_tap=self._more_menu))
        self.space(4)
        self._latest_slot = self.list.count() - 1
        self.section("top songs")
        self._top_note = Notice("loading…" if backend.live else "")
        self.add(self._top_note)
        self._albums_slot = self.list.count() - 1
        self._show_albums([e for e in entries if e.get("kind") == "album"])
        backend.search_async(name, "songs", lambda rows, n=name: self._on_top_songs(n, rows))
        if "library" in (self._kind or "").lower() and backend.live:
            # library artist: only the library's albums came back; get the catalog artist
            backend.search_async(name, "artists", lambda rows, n=name: self._on_catalog_artist(n, rows))

    def _on_top_songs(self, name, rows):
        if not self.isVisible() or getattr(self, "_top_note", None) is None:
            return
        low = name.lower()
        songs = [r for r in rows if r.get("kind") == "song" and low in (r.get("artist", "") or "").lower()][:5]
        idx = self.list.indexOf(self._top_note)
        self.list.takeAt(idx).widget().deleteLater()
        self._top_note = None
        self._entries = songs
        if not songs:
            self.list.insertWidget(idx, Notice("no popular songs found"))
            return
        for i, e in enumerate(songs):
            row = Row(rtitle(e), e.get("subtitle", ""), e.get("durationMs", 0),
                      art=e.get("artworkTemplate", ""), available=is_available(e),
                      on_tap=lambda i=i: self._play_from(i), on_hold=lambda e=e: song_menu(self, e))
            self.list.insertWidget(idx + i, row)
        prewarm(songs, GRID_ART)

    def _on_catalog_artist(self, name, rows):
        art = next((r for r in rows if r.get("kind") == "artist" and rtitle(r).lower() == name.lower()), None)
        if art is not None:
            backend.open_page_async(art.get("pageKind", "artist"), art.get("id", ""),
                                    lambda hdr, ents: self._on_catalog_albums(ents))

    def _on_catalog_albums(self, entries):
        if self.isVisible():
            self._show_albums([e for e in entries if e.get("kind") == "album"])

    def _show_albums(self, albums):
        """(Re)build latest release + albums + singles/EPs at their slot."""
        for w in getattr(self, "_alb_widgets", []):
            self.list.removeWidget(w)
            w.deleteLater()
        self._alb_widgets = []
        if not albums:
            return
        full, small = _split_discography(albums)
        newest = max(albums, key=lambda a: str(a.get("year") or ""))
        pos = [self._albums_slot]

        def put(w):
            self.list.insertWidget(pos[0], w)
            pos[0] += 1
            self._alb_widgets.append(w)

        def label(text):
            from PySide6.QtWidgets import QLabel
            lab = QLabel(text)
            lab.setFont(ztos._font(ztos.FONT_REGULAR, 13))
            lab.setStyleSheet("color: rgba(255,255,255,0.6); padding-top: 14px; padding-bottom: 4px;")
            put(lab)

        def open_album(al):
            ztos.App.current.push(DetailPage(al.get("pageKind", "album"), al.get("id", ""), rtitle(al)))

        label("latest release")
        put(Row(rtitle(newest).replace(" - Single", "").replace(" - EP", ""), newest.get("subtitle", ""),
                art=newest.get("artworkTemplate", ""), on_tap=lambda: open_album(newest)))
        for text, group in (("albums", full), ("singles & EPs", small)):
            if group:
                label(text)
                grid = AlbumGrid(group, on_tap=open_album)
                put(grid)
                grid.build_cells()
        prewarm(albums, GRID_ART)

    def _play_from(self, i):
        """Tap a track row: play from that row, the rest of the list in queue
        (play {ids, index} like the original: track_row.rs / link.rs)."""
        import player
        ztos.haptic("tap")
        sent, reason = backend.play_list(self._entries, i)
        if not sent:
            ztos.notify("cannot play", reason or "slipmatd not ready")
            return
        if reason:
            ztos.notify("unavailable", reason)
        ztos.App.current.push(player.NowPlaying(ztos.App.current))

    def _header_block(self, header, n_others=0):
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
        meta = QLabel(f"{n} tracks · {fmt_ms(total)}" if n else (f"{n_others} albums" if n_others else ""))
        meta.setFont(ztos._font(ztos.FONT_REGULAR, 13))
        meta.setStyleSheet("color: rgba(255,255,255,0.45);")
        tv.addWidget(name)
        tv.addWidget(sub)
        tv.addWidget(meta)
        tv.addStretch(1)
        lay.addWidget(texts, 1)
        self.add(row)
        # action row: play / shuffle / queue / more (detail_page.rs header buttons)
        if not n:                       # artist page: albums only, nothing to play/shuffle
            self.space(4)
            return
        actions = self.round_buttons(
            CircleButton(icons.path("play"), on_tap=self._play_all),
            CircleButton(icons.path("shuffle"), on_tap=self._play_shuffled),
            CircleButton(icons.path("queue"), on_tap=self._enqueue_all),
            CircleButton(icons.path("more"), on_tap=self._more_menu))
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
        self._sort_btn = CircleButton(icons.path("sort"), "sort", self._sort_menu)
        self.bar(self._sort_btn,
                 CircleButton(icons.path("search"), "search",
                                  lambda: app.push(screens.SearchPage())),
                 CircleButton(icons.path("queue"), "queue",
                                  lambda: app.push(screens.QueuePage())),
                 CircleButton(icons.path("play"), "now playing",
                                  lambda: app.push(player.NowPlaying(app))))
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
