# IPC.md — the `slipmatd` socket protocol (as read from the sources)

Source: Slipmat 0.12.0 (GPL-3.0-or-later). `file:line` citations re-read on
2026-11-07. Existing client reference: `crates/climat/src/link.rs` (106 lines).

## 1. Transport

- Unix socket: `$XDG_RUNTIME_DIR/slipmat.sock`
  (`crates/slipmat-core/src/ipc.rs:31-38`, `socket_path`).
- **Newline-delimited JSON**: one message per line, `\n` at the end
  (`crates/slipmatd/src/serve.rs:732-734`: `serde_json::to_vec(&event)` +
  `line.push(b'\n')` + `write_all`).
- If the socket is missing, the first client **starts the daemon** (same
  directory as the executable) with `setsid` and waits up to 10 s for it to
  listen (`ipc.rs:48-108`, `connect_or_spawn`).
- One connection = one stream: requests go out and events come in; **the
  answer to a request arrives as an event**, not paired with it
  (`climat/src/link.rs:5-11`). On connect the client immediately sends
  `subscribe`, `stage`, `snapshot`, `queue` (`climat/src/link.rs:96-101`).
- Events are broadcast to all clients (`serve.rs:57` `events:
  broadcast::Sender<Event>`, `:187` `broadcast::channel(BACKLOG)`).

## 2. Naming conventions

- Fields are **snake_case**, tags are **camelCase** (`ipc.rs:13-15`).
- `Request` is `#[serde(tag = "req")]`, `Event` is `#[serde(tag = "event")]`
  (`ipc.rs:120-121`, `:416-417`).
- The client sends **intents**, never state; the daemon is the only owner of
  the queue and the state (`ipc.rs:17-20`).

## 3. Client → daemon: `Request` (`ipc.rs:123-272`)

| `req` tag | fields | line |
|---|---|---|
| `transport` | `Transport` (see §5) | :126 |
| `jumpTo` | `{index}` | :131 |
| `snapshot` | — | :136 |
| `queue` | — | :140 |
| `stage` | — | :148 |
| `subscribe` | — | :152 |
| `signIn` | — (shows the Apple window) | :160 |
| `signOut` | — | :165 |
| `browse` | `{view, query="", offset=0, limit=0, sort, reverse=false}` — `limit=0` = "the rest"; the daemon sorts BEFORE windowing | :170 |
| `search` | `{query, filter=all, offset=0}` — searches the whole Apple catalog | :197 |
| `open` | `{kind, id}` — opens an album/artist/playlist (catalog or library) | :209 |
| `enqueue` | `{ids, next=false}` — queues without rebuilding the queue | :216 |
| `removeFromQueue` | `{index}` | :225 |
| `moveInQueue` | `{from, to}` | :230 |
| `clearQueue` | — | :234 |
| `write` | `{action, id}` — favorite/unfavorite/addToLibrary/removeFromLibrary | :238 |
| `refresh` | — (re-reads the library from Apple) | :243 |
| `play` | `{ids, index=0, start=clicked\|inOrder\|shuffled}` — builds the queue and starts | :251 |
| `quit` | — (refused if other clients are attached) | :270 |

Wire examples (from the tests in `ipc.rs:563-576`):
`{"req":"transport","cmd":"seek","position_ms":4200}`,
`{"req":"subscribe"}`.

### Supporting enums

- `View` (`ipc.rs:339`): `songs | albums | artists | playlists`.
- `SortBy` (`slipmat-core/src/sort.rs:23-40`): `title | artist | album | year |
  added | updated`; per view: songs→title/artist/album/year,
  albums→title/artist/year/added, playlists→title/added/updated,
  artists→title (`sort.rs:52-59`).
- `CatalogFilter` (`ipc.rs:281`): `all | songs | albums | artists | playlists`
  → `types=songs,albums,artists,playlists` etc. (`ipc.rs:305-318`).
- `PageKind` (`ipc.rs:354`): `album | artist | playlist | libraryAlbum |
  libraryArtist | libraryPlaylist` — catalog and library ids are **not**
  interchangeable (`ipc.rs:357-364`).
- `PlayMode` (`ipc.rs:370`): `clicked | inOrder | shuffled`.
- `WriteAction` (`ipc.rs:329`): `favorite | unfavorite | addToLibrary |
  removeFromLibrary`.

## 4. Daemon → client: `Event` (`ipc.rs:418-489`)

| `event` tag | payload | line |
|---|---|---|
| `snapshot` | `Snapshot` (flat current track, see §6) | :420 |
| `queue` | `{items: [QueueItem], position}` — the whole list | :426 |
| `stage` | `Stage` with tag `stage`: `connecting | ready | signedOut | broken{detail}` | :433 |
| `rows` | `{view, entries: [Entry], total}` — answer to `browse` | :437 |
| `results` | `{query, entries, offset, more}` — answer to `search` | :451 |
| `page` | `{kind, id, header: Entry, entries: [Entry]}` — answer to `open` | :466 |
| `libraryChanged` | — invalidation; the client re-requests the page it draws | :477 |
| `libraryRefreshing` | `{refreshing: bool}` | :481 |
| `error` | `{detail}` | :485 |

## 5. `Transport` (`ipc.rs:394-416`), `cmd` tag in camelCase

`play | pause | playPause | next | previous |
seek{position_ms} (absolute, ms) | setVolume{volume: f64 0..1} |
setShuffle{shuffle: bool} | setRepeat{mode}` with `RepeatMode` =
`none | one | all` (lowercase, `player/protocol.rs:186-191`).

## 6. Data structures

- `Snapshot` (`ipc.rs:520-543`): `track_id?, title, artist, album,
  art_path? (an already downloaded local file), position_ms, duration_ms,
  playing, busy, volume, shuffle, repeat, can_next, can_previous`.
- `QueueItem` (`ipc.rs:496-517`): `id?, title, artist, album, duration_ms`
  (`id` = catalog id if there is one, else library id; opaque, it goes back in
  `jumpTo`).
- `Entry` (`slipmat-core/src/entry.rs:18-24`), `kind` tag in camelCase:
  `song(Track) | album(Album) | artist(Artist) | playlist(Playlist)`.
  - `Track` (`music/types.rs:23-73`): `date_added, year, favorite, in_library,
    library_id?, id, catalog_id? (None = not streamable), title, artist, album,
    duration_ms, track_number, artwork?`.
  - `Artwork` (`types.rs:91-127`): a **URL template**
    `https://is1.mzstatic.com/image/thumb/.../{w}x{h}bb.jpg`;
    `url(size)` substitutes `{w}/{h}/{f}` (`types.rs:107-113`);
    `cache_key()` = FNV-1a of the template (`types.rs:116-126`).
    The daemon serves the current track's cover as a local `art_path` in the
    `Snapshot`; list covers come from the `artwork` template carried by the
    `Entry` objects of `browse`/`open` (this app downloads and caches them,
    see `art.py`).
  - `Album` (`types.rs:130-148`): `id, date_added, name, artist, artwork?,
    year, track_count, library`.
  - `Playlist` (`types.rs:150-175`): `id, date_added, last_modified, name,
    curator, description, artwork?, library`.
  - `Artist` (`types.rs:177-187`): `id, name, artwork?, genres, library`.
  - `Entry::subtitle()` (`entry.rs:44-66`): song → `"artist — album"`;
    album → `"artist · year"`; artist → genres; playlist → curator.
  - `Entry::page_target()` (`entry.rs:78-99`): album/artist/playlist open a
    page (library `PageKind` if `library=true`).
- `format_duration(ms)` → `m:ss` or `h:mm:ss` (`types.rs:75-82`).

## 7. Daemon-side dispatch (`slipmatd/src/serve.rs`)

`Request::Transport → :921`, `Browse → :794`, `Search → :820`, `Open → :828`,
`Play → :852`, `Enqueue → :856`, `Snapshot/Stage/Queue → :776-781`,
`JumpTo → :782`. Snapshots are also pushed on their own on state changes
(`serve.rs:157` `publish(Event::Snapshot(...))`).
