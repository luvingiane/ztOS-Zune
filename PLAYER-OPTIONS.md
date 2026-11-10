# PLAYER-OPTIONS.md — the options menu of "now playing"

Reference: a screenshot of Apple Music's context menu on iPhone supplied by the
owner (no code read or copied, see PROVENANCE.md). Daemon sources:
Slipmat 0.12.0 `crates` (GPL-3.0-or-later, read). Apple Music API docs:
developer.apple.com.

## Table

| Entry | What it does in Apple Music | What slipmatd offers today | State in this app |
|---|---|---|---|
| Download | offline download | nothing | **excluded by the owner: not shown** |
| Add to favorites | star on/off | `write favorite`/`unfavorite` — `slipmat-core/src/ipc.rs:329-337` (WriteAction), handler `slipmatd/src/serve.rs:1023-1062`; favorite via `POST /me/favorites` (`music/client.rs:288-295`), unfavorite via the sidecar `Command::Unfavorite` (`player/protocol.rs:135`). Note: `DELETE /me/favorites` returns 400 (permissions), documented in `client.rs:297-310`, which is why unfavorite goes through the sidecar | **done** (`player.OptionsMenu`, visible state: "remove from favorites" label + flag from the rows) |
| Go to album | opens the album page | `open` with PageKind album/libraryAlbum — `ipc.rs:209-210, 344-356`; answered by a `page` event | **done** (matched by name in `browse("albums")` → `DetailPage`) |
| Go to artist | opens the artist page | same `open` with artist/libraryArtist | **done** |
| shuffle / repeat (discrete state) | — | `transport setShuffle/setRepeat` — `ipc.rs:394-416` (Transport), the snapshot carries `shuffle`/`repeat` | **done** (in the options menu, with state; the owner wanted them there) |
| Share | iOS share sheet | **ztOS has no share mechanism**: `sdk/runtime/ztos/ial.py` is hardware only (Power1/Haptics1…), the only "share" is a glyph icon; no intent/share sheet in `ztmetro/` (checked with grep) | **not done, not faked**: entry absent. ztOS would need a `share …` line on `ztmetro.ctl` plus a shell chooser (or a `ztos.share(text, url)` API) |
| Pin the song | pin on top of the library | no public Apple Music API for pins | **not feasible** (no API) |
| Add to playlist | adds the song to a library playlist | the daemon only reads playlist tracks (`music/client.rs:384,718`); no writes | **feasible with a daemon patch**: a new `Request::AddToPlaylist{playlist,song}` in `ipc.rs` + a handler in `serve.rs` + `POST /v1/me/library/playlists/{id}/tracks` with `ids[songs]` in `client.rs`. Not implemented; the entry is not shown |
| Create station | radio station from the song | none | **feasible with a daemon patch**: Apple Music API has Stations (`POST /v1/catalog/{storefront}/songs/{id}/station`), then `play` the station's tracks. Not implemented; entry absent |
| Suggest less (dislike) | "dislike" rating | ratings exist but the daemon does not use them | **feasible with a daemon patch**: `PUT /v1/me/ratings/songs/{id}` `{"type":"dislike"}` (needs a Music-User-Token, which the daemon has). Not implemented; entry absent |
| View credits | credits page | no public API for song credits | **not feasible** (no public API) |

Rule followed: the menu only shows entries that do something real (tested on a
fake socket: `write` and `open` end up on the wire — `tests/test_player.py`).
The others are documented here, not faked.
