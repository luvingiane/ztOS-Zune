# FEATURES-PARITY.md — original Slipmat frontend vs this app

Original frontend: `~/oneplus2/build/slipmat/Slipmat-0.12.0/crates/slipmat/src`
(GPL-3.0-or-later — read, not copied). "Ours" = this repo: `hub.py`,
`screens.py`, `client.py`, `art.py`.

| Original feature (file:line) | State in our app | Where / note |
|---|---|---|
| Library sections songs/albums/artists/playlists (`app/library.rs`, `ipc::View`) | **fatta** | pivot in `hub.py`, `backend.browse` |
| Catalog search with filter (`app/view.rs:96-135` SearchScope, `ipc::Request::Search`) | **fatta** | `screens.SearchPage` + filter menu (all/songs/albums/artists/playlists), `backend.search` |
| Per-section sort + direction, persisted (`app/view.rs:325-360` Sorts, `sort.rs` SortBy) | **fatta** | sort button in the pivot app bar, `hub.get_sort/set_sort` in `ztos.store`, `browse(sort, reverse)`; songs have no "added" (Apple sends no dateAdded for library songs — `types.rs:366-373`, measured 0/541) so songs+"added" is joined via the albums' date_added client-side (`client.py`) |
| Row context menu: play next / add to queue / favorite / add-remove library (`app/row_menu.rs:31-62`, `WriteAction`) | **fatta** | hold on a song row in `hub.SongsPage._menu`, `backend.write/enqueue` |
| Album/artist/playlist detail pages (`components/detail_page.rs`, `app/pages.rs`, `ipc::Request::Open`) | **fatta (stage 4)** | `hub.DetailPage`: metro header (cover 140 + name light + artist/curator + "N tracks · total"), action row play/shuffle/queue/more (add/remove library), track rows with 48px thumbs |
| Detail header transport buttons Play/Shuffle/Queue (`detail_page.rs:119-237`) | **fatta** | action row in `hub.DetailPage._header_block`; play sends catalog ids like the original (`play_list`) |
| Row artwork thumbs (`components/artwork.rs`, `track_row.rs`) | **fatta (stage 4)** | `widgets.Row` art param: 48px thumb, async from disk cache, neutral grey placeholder, no letters |
| Artwork fetch + cache (`artwork.rs`, FNV cache key `types.rs:116-126`) | **fatta (stage 4, bugfix)** | `art.py`: QThread worker (the phone crash was `QThread.create`, nonexistent in PySide6), 24 MB disk cap with eviction, 24 MB RAM cap, real-download test `tests/test_art.py` |
| Play from a list = all catalog ids + index (`app/queue.rs:30-55`, `climat/main.rs:632`) | **fatta (stage 4, bugfix)** | `backend.play_list`; unplayable row (catalog_id null) -> clear message, library id never sent; tests on fake socket |
| Daemon start/reconnect (`daemon.rs`, `serve.rs`) | **fatta (stage 4)** | `client._ensure_daemon`: socket → `systemctl --user start slipmatd` → `/usr/bin/slipmatd`, non-blocking, one attempt, auto-reconnect backoff 2s→30s |
| Per-view sort incl. songs "recently added" (`app/view.rs:325-360`, `sort.rs`) | **fatta (stage 4)** | sort menu on every list; songs+"added" = client-side join on albums' date_added (Apple sends no dateAdded for library songs — proof in STATO.md) |
| Album grid + mosaic + covers (`components/grid_item.rs`, `mosaic.rs`, `cover.rs`, `artwork.rs`) | **parziale** | grid with real artwork in `hub.AlbumGrid`/`art.Artwork` (template → FNV cache → async fetch); no mosaic (Apple playlists have no mosaic art here) |
| Now playing: cover, seek, transport, volume, shuffle, repeat (`components/now_playing.rs`, `player_view/transport.rs`) | **fatta** | `screens.NowPlaying`: art_path/cover, SeekBar, prev/play/next, volume slider, shuffle/repeat, queue button |
| Queue view: jump, remove, move, clear, current highlight (`components/queue_view/`) | **parziale** | `screens.QueuePage`: accent current, tap=jumpTo, hold=remove, clear; move (drag) manca — the SDK list has no drag-reorder |
| Play/enqueue/jumpTo (`ipc::Request::Play/Enqueue/JumpTo`) | **fatta** | `client.py` + song row tap/hold |
| Library writes favorite/add/remove (`app/writes.rs`, `Request::Write`) | **fatta** | hold menu on songs; `libraryChanged` event refills the visible page (`hub._refill`) |
| Refresh library (`Request::Refresh`) | **fatta** | settings "refresh library" |
| Sign in/out + daemon stage (`Request::SignIn/SignOut`, `Event::Stage`, `app/status.rs`) | **fatta** | settings shows stage/mode live; sign in/out entries; demo only when not ready, with notice |
| Notifications on track change (`notify.rs:34`) | **parziale** | `backend.error` → `ztos.notify`; track-change notification manca (servirebbe confrontare snapshot successive in `client.py`) |
| MPRIS (`mpris.rs`) | **manca** (non serve su ztOS: la shell ha il suo player chrome) | — |
| Pins (`app/pins/`) | **manca** (ztOS ha le sue tile: `ztos.tile_update` disponibile se serve) | — |
| OSD volume (`app/osd.rs`) | **parziale** | volume slider in Now Playing; niente OSD (la shell lo disegna lei) |
| Empty/loading states per section (`app/status.rs:26-33`) | **fatta** | `hub.Notice` rows (demo notice / loading / error) |
| Settings UI (`settings.rs`) | **parziale** | minima: sign in/out, refresh, quit, about+accent+stage (S1/S2) |

Legend: fatta = implementata e testata; parziale = presente con périmètre ridotto;
manca = non implementata (con motivo).
