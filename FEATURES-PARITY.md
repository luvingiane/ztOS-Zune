# FEATURES-PARITY.md — original Slipmat frontend vs this app

Original frontend: Slipmat 0.12.0, `crates/slipmat/src`
(GPL-3.0-or-later — read, not copied). "Ours" = this repo: `hub.py`,
`screens.py`, `client.py`, `art.py`.

| Original feature (file:line) | State in our app | Where / note |
|---|---|---|
| Library sections songs/albums/artists/playlists (`app/library.rs`, `ipc::View`) | **done** | pivot in `hub.py`, `backend.browse` |
| Catalog search with filter (`app/view.rs:96-135` SearchScope, `ipc::Request::Search`) | **done** | `screens.SearchPage` + filter menu (all/songs/albums/artists/playlists), `backend.search` |
| Per-section sort + direction, persisted (`app/view.rs:325-360` Sorts, `sort.rs` SortBy) | **done** | sort button in the pivot app bar, `hub.get_sort/set_sort` in `ztos.store`, `browse(sort, reverse)`; songs have no "added" (Apple sends no dateAdded for library songs — `types.rs:366-373`, measured 0/541) so songs+"added" is joined via the albums' date_added client-side (`client.py`) |
| Row context menu: play next / add to queue / favorite / add-remove library (`app/row_menu.rs:31-62`, `WriteAction`) | **done** | hold on a song row in `hub.SongsPage._menu`, `backend.write/enqueue` |
| Album/artist/playlist detail pages (`components/detail_page.rs`, `app/pages.rs`, `ipc::Request::Open`) | **done** | `hub.DetailPage`: metro header (cover 140 + name light + artist/curator + "N tracks · total"), action row play/shuffle/queue/more (add/remove library), track rows with 48px thumbs |
| Detail header transport buttons Play/Shuffle/Queue (`detail_page.rs:119-237`) | **done** | action row in `hub.DetailPage._header_block`; play sends catalog ids like the original (`play_list`) |
| Row artwork thumbs (`components/artwork.rs`, `track_row.rs`) | **done** | `widgets.Row` art param: 48px thumb, async from disk cache, neutral grey placeholder, no letters |
| Artwork fetch + cache (`artwork.rs`, FNV cache key `types.rs:116-126`) | **done** | `art.py`: QThread worker (the phone crash was `QThread.create`, nonexistent in PySide6), 24 MB disk cap with eviction, 24 MB RAM cap, real-download test `tests/test_art.py` |
| Play from a list = all catalog ids + index (`app/queue.rs:30-55`, `climat/main.rs:632`) | **done** | `backend.play_list`; unplayable row (catalog_id null) -> clear message, library id never sent; tests on fake socket |
| Daemon start/reconnect (`daemon.rs`, `serve.rs`) | **done** | `client._ensure_daemon`: socket → `systemctl --user start slipmatd` → `/usr/bin/slipmatd`, non-blocking, one attempt, auto-reconnect backoff 2s→30s |
| Per-view sort incl. songs "recently added" (`app/view.rs:325-360`, `sort.rs`) | **done** | sort menu on every list; songs+"added" = client-side join on albums' date_added (Apple sends no dateAdded for library songs — measured on a real library) |
| Album grid + mosaic + covers (`components/grid_item.rs`, `mosaic.rs`, `cover.rs`, `artwork.rs`) | **partial** | grid with real artwork in `hub.AlbumGrid`/`art.Artwork` (template → FNV cache → async fetch); no mosaic (Apple playlists have no mosaic art here) |
| Now playing: cover, seek, transport, volume, shuffle, repeat (`components/now_playing.rs`, `player_view/transport.rs`) | **done** | `screens.NowPlaying`: art_path/cover, SeekBar, prev/play/next, volume slider, shuffle/repeat, queue button |
| Queue view: jump, remove, move, clear, current highlight (`components/queue_view/`) | **partial** | `screens.QueuePage`: accent current, tap=jumpTo, hold=menu remove, clear; drag-reorder: see the "Queue drag-to-reorder" row below |
| Play/enqueue/jumpTo (`ipc::Request::Play/Enqueue/JumpTo`) | **done** | `client.py` + song row tap/hold |
| Library writes favorite/add/remove (`app/writes.rs`, `Request::Write`) | **done** | hold menu on songs; `libraryChanged` event refills the visible page (`hub._refill`) |
| Refresh library (`Request::Refresh`) | **done** | settings "refresh library" |
| Sign in/out + daemon stage (`Request::SignIn/SignOut`, `Event::Stage`, `app/status.rs`) | **done** | settings shows stage/mode live; sign in/out entries; empty pages with a notice when the daemon is not ready |
| Notifications on track change (`notify.rs:34`) | **partial** | `backend.error` → `ztos.notify`; see the track-change notifications row below |
| MPRIS (`mpris.rs`) | **missing** (not needed on ztOS: the shell has its own player chrome) | — |
| Pins (`app/pins/`) | **missing** (ztOS has its own tiles: `ztos.tile_update` is available if needed) | — |
| OSD volume (`app/osd.rs`) | **partial** | volume slider in Now Playing; no OSD (the shell draws it) |
| Empty/loading states per section (`app/status.rs:26-33`) | **done** | `hub.Notice` rows (offline notice / loading / error) |
| Settings UI (`settings.rs`) | **partial** | minimal: sign in/out, refresh, quit, about+accent+stage (S1/S2) |

Legend: done = implemented and tested; partial = present with a reduced scope;
missing = not implemented (with the reason).

| Tap a track row plays from that row (`play{ids,index}`) | **done** | `hub.DetailPage._play_from` → `backend.play_list` |
| Queue drag-to-reorder (`MoveInQueue`) | **redone** | `screens.QueuePage`: drag handle (grip, a QAbstractSlider so the SDK finger filter leaves it alone) on every row; the row is lifted, others make room live, auto-scroll at the edges, release → `moveInQueue{from,to}`; the old long-press hack did not work on B |
| Live tile (TILE-SIGNALS.md) | **done** | `client.py` on each snapshot → `ztos.tile_update`; cleared on stop |
| Track-change notifications off by default (`settings.rs:122,385-387`) | **done** | toggle in Settings, default off |
| Playlist mosaic 2x2 (`components/mosaic.rs`) | **done** | `art.mosaic_image` + playlist header without artwork |
| Signed/expiring artwork URLs | **done** | cache keyed by the URL hash, `art.stale` → re-browse |
| Seek position model (monotonic, staleness guard) | **done** | `player.PlayerSeek.anchor/current_pos` |
| Search grouped by category + filter chips  | **done** | `screens.SearchPage`: Artists / Albums / Songs / Playlists sections, chips all/songs/albums/artists/playlists, "see all"; song tap plays the song results from that row |
| Artist page  | **done (daemon limit)** | `open` on an artist returns ALBUM entries only (verified on B 10/11): the page lists the albums, each opens its page; no "top songs" (the daemon does not send them) |
| Unavailable tracks  | **done** | row dimmed + slashed-circle mark when `catalog_id` is null or the id is in the daemon's `~/.cache/slipmat/unplayable.json`; `play_list` skips them and starts from the next available with a notice |
| Player standard ztmetro  | **done** | `player.NowPlaying` = `ztos.Page` + `ztos.SeekBar` + 5 `CircleButton` in the app bar + `ztos.menu` options; optional blurred background (Settings toggle) computed on a worker thread |
| MPRIS / shell media banner | **da verificare** | the official `music` app is an MPRIS player (mpv-mpris) so the shell banner/volume show it; slipmatd MPRIS exposure not verified here |
