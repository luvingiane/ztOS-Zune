# PLAYER-OPTIONS.md — menu Opzioni di "In reproduction" (Now Playing)

Riferimento: screenshot del proprietario del 7/11 (menu contestuale di Apple
Music su iPhone, in italiano — `docs/shots/41-ref-options-menu.png`, osservato
da: screenshot del proprietario del 7/11; nessun codice letto/copiato, vedi
PROVENANCE.md). Fonti demone: `~/oneplus2/build/slipmat/Slipmat-0.12.0/crates`
(GPL-3.0-or-later, lette). Fonti Apple Music API: developer.apple.com.

## Tabella voci

| Voce (screenshot) | Cosa fa in Apple Music | Cosa offre slipmatd oggi | Stato in questa app |
|---|---|---|---|
| Scarica | scarica offline | niente | **esclusa dal proprietario: non compare** |
| Aggiungi ai preferiti | star on/off | `write favorite`/`unfavorite` — `slipmat-core/src/ipc.rs:329-337` (WriteAction), handler `slipmatd/src/serve.rs:1023-1062`; favorite via `POST /me/favorites` (`music/client.rs:288-295`), unfavorite via sidecar `Command::Unfavorite` (`player/protocol.rs:135`). Nota: `DELETE /me/favorites` dà 400 (permessi) — documentato in `client.rs:297-310`, per questo unfavorite passa dal sidecar | **fatta** (`player.OptionsMenu`, stato visibile: etichetta "Rimuovi dai preferiti" + flag dai rows) |
| Vai all'album (titolo sotto) | apre la pagina album | `open` con PageKind album/libraryAlbum — `ipc.rs:209-210, 344-356`; risposta evento `page` | **fatta** (match per nome in `browse("albums")` → `DetailPage`) |
| Vai all'artista (nome sotto) | apre la pagina artista | stesso `open` con artist/libraryArtist | **fatta** |
| shuffle / repeat (stato discreto) | — | `transport setShuffle/setRepeat` — `ipc.rs:394-416` (Transport), snapshot porta `shuffle`/`repeat` | **fatte** (nel menu Opzioni, con stato; il owner le ha volute lì) |
| Condividi / Condividi testo | share sheet iOS | **ztOS non ha alcun meccanismo di share**: `sdk/runtime/ztos/ial.py` è solo hardware (Power1/Haptics1…), l'unica "share" è un'icona glyph (`sdk/runtime/ztos/__init__.py:1466,1511`); nessun intent/share-sheet in `ztmetro/` (grep verificata) | **non fatta, non inventata**: voci assenti. Servirebbe a ztOS: una riga `share …` su `ztmetro.ctl` + un chooser della shell (o un'API `ztos.share(text,url)`), poi la usiamo |
| Metti brano in evidenza (pin) | pin in alto nella libreria | nessuna API pubblica Apple Music per i pin | **non fattibile** (no API) |
| Aggiungi alla playlist | aggiunge il brano a una playlist libreria | il demone legge solo i brani delle playlist (`music/client.rs:384,718`); nessuna scrittura | **fattibile con patch al demone**: nuova `Request::AddToPlaylist{playlist,song}` in `ipc.rs` + handler in `serve.rs` + `POST /v1/me/library/playlists/{id}/tracks` con `ids[songs]` in `client.rs`. Non implementata ora (build aarch64 del demone non fatto in questa sessione); la voce non compare nel menu |
| Crea stazione | stazione radio dal brano | nessuna | **fattibile con patch al demone**: Apple Music API ha Stations (`POST /v1/catalog/{storefront}/songs/{id}/station`, doc "Stations"), poi `play` dei brani della stazione. Non implementata ora; voce assente |
| Meno suggerimenti (dislike) | rating "non mi piace" | ratings esiste ma il demone non la usa ("the older love/dislike rating", `client.rs:288`) | **fattibile con patch al demone**: `PUT /v1/me/ratings/songs/{id}` `{"type":"dislike"}` (doc "Add a Personal Song Rating", richiede Music-User-Token — il demone ce l'ha). Non implementata ora; voce assente |
| Visualizza i riconoscimenti (credits) | pagina crediti | nessuna API pubblica per i credits delle canzoni | **non fattibile** (no API pubblica) |

Regola seguita: nel menu compaiono solo voci che fanno qualcosa di vero
(testate su socket finto: `write` e `open` finiscono sul wire —
`tests/test_player.py`). Le altre sono documentate qui, non finte.
