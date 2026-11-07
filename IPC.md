# IPC.md — protocollo del socket di `slipmatd` (come letto dai sorgenti)

Sorgente: Slipmat 0.12.0 in `~/oneplus2/build/slipmat/Slipmat-0.12.0`
(GPL-3.0-or-later). Citazioni `file:riga` rilette il 2026-11-07.
Riferimento client esistente: `crates/climat/src/link.rs` (106 righe).

## 1. Trasporto

- Socket Unix: `$XDG_RUNTIME_DIR/slipmat.sock`
  (`crates/slipmat-core/src/ipc.rs:31-38`, `socket_path`).
- **Newline-delimited JSON**: un messaggio per riga, `\n` in coda
  (`crates/slipmatd/src/serve.rs:732-734`: `serde_json::to_vec(&event)` +
  `line.push(b'\n')` + `write_all`).
- Se il socket non c'è, il primo client **avvia il demone** (stesso dir
  dell'eseguibile) con `setsid` e aspetta fino a 10 s che si metta in ascolto
  (`ipc.rs:48-108`, `connect_or_spawn`).
- Una connessione = un flusso: si mandano richieste e arrivano eventi; **la
  risposta a una richiesta arriva come evento**, non accoppiata
  (`climat/src/link.rs:5-11`). Al connect il client manda subito
  `subscribe`, `stage`, `snapshot`, `queue` (`climat/src/link.rs:96-101`).
- Gli eventi sono broadcast a tutti i client (`serve.rs:57` `events:
  broadcast::Sender<Event>`, `:187` `broadcast::channel(BACKLOG)`).

## 2. Convenzioni dei nomi

- Campi **snake_case**, tag **camelCase** (`ipc.rs:13-15`).
- `Request` è `#[serde(tag = "req")]`, `Event` è `#[serde(tag = "event")]`
  (`ipc.rs:120-121`, `:416-417`).
- Il client manda **intenti**, mai stato; il demone è l'unico che possède
  coda e stato (`ipc.rs:17-20`).

## 3. Client → demone: `Request` (`ipc.rs:123-272`)

| tag `req` | campi | riga |
|---|---|---|
| `transport` | `Transport` (vedi §5) | :126 |
| `jumpTo` | `{index}` | :131 |
| `snapshot` | — | :136 |
| `queue` | — | :140 |
| `stage` | — | :148 |
| `subscribe` | — | :152 |
| `signIn` | — (mostra la finestra Apple) | :160 |
| `signOut` | — | :165 |
| `browse` | `{view, query="", offset=0, limit=0, sort, reverse=false}` — `limit=0` = "tutto il resto"; il demone ordina PRIMA di fare la finestra | :170 |
| `search` | `{query, filter=all, offset=0}` — cerca in tutto il catalogo Apple | :197 |
| `open` | `{kind, id}` — apre album/artista/playlist (catalog o library) | :209 |
| `enqueue` | `{ids, next=false}` — accoda senza ricostruire la coda | :216 |
| `removeFromQueue` | `{index}` | :225 |
| `moveInQueue` | `{from, to}` | :230 |
| `clearQueue` | — | :234 |
| `write` | `{action, id}` — favorite/unfavorite/addToLibrary/removeFromLibrary | :238 |
| `refresh` | — (ri-legge la libreria da Apple) | :243 |
| `play` | `{ids, index=0, start=clicked\|inOrder\|shuffled}` — costruisce la coda e parte | :251 |
| `quit` | — (rifiutato se altri client sono attaccati) | :270 |

Esempi wire (dai test in `ipc.rs:563-576`):
`{"req":"transport","cmd":"seek","position_ms":4200}`,
`{"req":"subscribe"}`.

### Enum di supporto

- `View` (`ipc.rs:339`): `songs | albums | artists | playlists`.
- `SortBy` (`slipmat-core/src/sort.rs:23-40`): `title | artist | album | year |
  added | updated`; per vista: songs→title/artist/album/year,
  albums→title/artist/year/added, playlists→title/added/updated,
  artists→title (`sort.rs:52-59`).
- `CatalogFilter` (`ipc.rs:281`): `all | songs | albums | artists | playlists`
  → `types=songs,albums,artists,playlists` ecc. (`ipc.rs:305-318`).
- `PageKind` (`ipc.rs:354`): `album | artist | playlist | libraryAlbum |
  libraryArtist | libraryPlaylist` — gli id catalog e library **non** sono
  intercambiabili (`ipc.rs:357-364`).
- `PlayMode` (`ipc.rs:370`): `clicked | inOrder | shuffled`.
- `WriteAction` (`ipc.rs:329`): `favorite | unfavorite | addToLibrary |
  removeFromLibrary`.

## 4. Demone → client: `Event` (`ipc.rs:418-489`)

| tag `event` | payload | riga |
|---|---|---|
| `snapshot` | `Snapshot` (brano corrente piatto, vedi §6) | :420 |
| `queue` | `{items: [QueueItem], position}` — lista intera | :426 |
| `stage` | `Stage` tag `stage`: `connecting | ready | signedOut | broken{detail}` | :433 |
| `rows` | `{view, entries: [Entry], total}` — risposta a `browse` | :437 |
| `results` | `{query, entries, offset, more}` — risposta a `search` | :451 |
| `page` | `{kind, id, header: Entry, entries: [Entry]}` — risposta a `open` | :466 |
| `libraryChanged` | — invalidazione, il client ri-chiede la pagina che disegna | :477 |
| `libraryRefreshing` | `{refreshing: bool}` | :481 |
| `error` | `{detail}` | :485 |

## 5. `Transport` (`ipc.rs:394-416`), tag `cmd` camelCase

`play | pause | playPause | next | previous |
seek{position_ms} (assoluto, ms) | setVolume{volume: f64 0..1} |
setShuffle{shuffle: bool} | setRepeat{mode}` con `RepeatMode` =
`none | one | all` (lowercase, `player/protocol.rs:186-191`).

## 6. Strutture dati

- `Snapshot` (`ipc.rs:520-543`): `track_id?, title, artist, album,
  art_path? (file locale già scaricato), position_ms, duration_ms, playing,
  busy, volume, shuffle, repeat, can_next, can_previous`.
- `QueueItem` (`ipc.rs:496-517`): `id?, title, artist, album, duration_ms`
  (`id` = catalog id se c'è, else library id; opaco, torna indietro in `jumpTo`).
- `Entry` (`slipmat-core/src/entry.rs:18-24`), tag `kind` camelCase:
  `song(Track) | album(Album) | artist(Artist) | playlist(Playlist)`.
  - `Track` (`music/types.rs:23-73`): `date_added, year, favorite, in_library,
    library_id?, id, catalog_id? (None = non streamabile), title, artist, album,
    duration_ms, track_number, artwork?`.
  - `Artwork` (`types.rs:91-127`): è un **template URL**
    `https://is1.mzstatic.com/image/thumb/.../{w}x{h}bb.jpg`;
    `url(size)` sostituisce `{w}/{h}/{f}` (`types.rs:107-113`);
    `cache_key()` = FNV-1a del template (`types.rs:116-126`).
    **I client non parlano con Apple per l'arte**: il demone serve `art_path`
    locale nello `Snapshot`; per le righe, `artwork.url(size)` si risolve in
    locale (la demo di Slipmat lo fa via cache; da verificare come `climat`
   /`slipmat` ottengono le copertine delle liste — in ogni caso il token Apple
    resta nel demone, il client può usare `art_path` dello snapshot e per le
    liste chiedere `browse`/`open` i cui `Entry` portano `artwork` template:
    da chiarire se il demone cachea anche quelle; in caso contrario il client
    mostra placeholder per le copertine di lista e usa `art_path` per il
    brano corrente).
  - `Album` (`types.rs:130-148`): `id, date_added, name, artist, artwork?,
    year, track_count, library`.
  - `Playlist` (`types.rs:150-175`): `id, date_added, last_modified, name,
    curator, description, artwork?, library`.
  - `Artist` (`types.rs:177-187`): `id, name, artwork?, genres, library`.
  - `Entry::subtitle()` (`entry.rs:44-66`): song → `"artista — album"`;
    album → `"artista · anno"`; artist → generi; playlist → curator.
  - `Entry::page_target()` (`entry.rs:78-99`): album/artist/playlist aprono
    pagina (`PageKind` library se `library=true`).
- `format_duration(ms)` → `m:ss` o `h:mm:ss` (`types.rs:75-82`).

## 7. Dispatch lato demone (`slipmatd/src/serve.rs`)

`Request::Transport → :921`, `Browse → :794`, `Search → :820`, `Open → :828`,
`Play → :852`, `Enqueue → :856`, `Snapshot/Stage/Queue → :776-781`,
`JumpTo → :782`. Gli snapshot vengono anche spinti da soli sui cambi di stato
(`serve.rs:157` `publish(Event::Snapshot(...))`).
