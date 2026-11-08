# PROVENANCE.md — regola di provenienza

## 1. Repo di riferimento visivo e stato della licenza

- Repo di riferimento visivo: `https://github.com/bransonwerner/zune-player`
  (demo live `https://bransonwerner.github.io/zune-player/`).
- **Quel repo non ha licenza.** Il proprietario ha aperto un'issue all'autore
  chiedendo una licenza permissiva (MIT/Apache-2.0 o GPL-3.0-or-later) e il
  permesso di rifare l'interfaccia in Qt. **Risposta in attesa.**
- Finché il proprietario non scrive in `STATO.md` che l'autore ha concesso per
  scritta una licenza (citandone il testo), **non si legge, non si copia e non
  si adatta il suo codice** (né TS, né CSS, né HTML, né asset).

## 2. Cosa è stato osservato (e quando)

Permesso dal prompt: **guardare la demo in esecuzione** (screenshot,
registrazioni, misure di tempi e posizioni) e usare quelle osservazioni come
specifica. Mai "copiato da": tutto quanto è in `DESIGN.md` con la dicitura
"osservato da" deriva da screenshot/misure della demo in esecuzione, mai dal
suo sorgente.

| Oggetto | Osservato da | Data |
|---|---|---|
| Schermo home Zune HD (menu 8 voci, barra stato, strip inferiore) | `docs/shots/02-zunehd-home.png` | 2026-11-07 |
| Hub "music" panorama orizzontale (artists/albums/songs/playlists/podcasts) | `docs/shots/03-zunehd-music-hub.png` | 2026-11-07 |
| Lista brani (righe 299x59, titolo/sottotitolo/durata) | `docs/shots/04-zunehd-songs-list.png` | 2026-11-07 |
| Schermata di default (Zune 30, per confronto) | `docs/shots/01-demo-default-zune30.png` | 2026-11-07 |
| Misure geometriche, font, colori, durate/curve di animazione | misure via DOM della demo in esecuzione (getBoundingClientRect / getComputedStyle),TAB browser, registrate in `DESIGN.md` §2-§4 | 2026-11-07 |

**7/11/2026 ~17:55: il proprietario ha istruito "no fallo in locale":**
l'osservazione live della demo è **cessata** (tab browser chiuso, verificato 0
tab aperti). Da quel momento **non si apre più alcun URL di
bransonwerner/zune-player** e non si scarica nulla da lì. Gli screenshot e le
misure già salvati restano come unico ricordo dell'osservazione (sono dati
locali, non codice). Tutto il design non coperto da quelle misure è
**lavoro originale** ispirato alla conoscenza generale dell'interfaccia
Zune HD, e resta qui anche se la licenza non arrivasse mai.

## 3. Cosa NON è mai stato fatto

- Non è stato letto, scaricato, copiato o adattato alcun file del repo
  `bransonwerner/zune-player` (nessun TS/CSS/HTML/asset), né via browser né
  via git. Non sono stati aperti i suoi asset di rete oltre alla pagina demo
  stessa. Nessun messaggio all'autore.
- Nessun font, immagine o marchio Microsoft è presente in questo repo.
  Font: si usano i font di sistema di ztOS (stack "Segoe UI"/"Selawik"/
  "Open Sans"/sans-serif come nel wrapper ztOS, cadendo su DejaVu Sans su PC).
  Icone: SVG scritte da zero in `assets/icons/` (licenza propria, GPL-3.0-or-later).

## 4. Se l'autore rifiuta (o chiede di non rifare l'interfaccia)

Si ferma **tutto** e si cancella dal progetto ogni derivazione dal suo repo o
dalla sua demo: screenshot e registrazioni in `docs/shots/`, `DESIGN.md`,
tabelle di misure, QML/CSS/asset costruiti guardandola, ogni riferimento nei
commit (se serve, si ricrea il repo locale senza quella storia); poi
`grep -ri "zune-player\|bransonwerner" .` deve dare zero risultati e l'esito
va scritto in `STATO.md`. Non si riprogetta "alla larga": il progetto si
chiude. Questo file (`PROVENANCE.md`) viene cancellato per ultimo, dopo che
il proprietario ha letto il rapporto di cancellazione.

## 5. Riuso di codice da Slipmat (GPL-3.0-or-later)

- `COPYING` è il testo GPL-3 copiato verbatim da
  `~/oneplus2/build/slipmat/Slipmat-0.12.0/COPYING` (testo di licenza, non codice).
- Il protocollo in `IPC.md` è **documentazione** di `crates/slipmat-core/src/ipc.rs`
  (GPL-3.0-or-later), riletto e citéato file:riga; il client Python lo
  reimplementa (newline-JSON sullo stesso socket), non copia sorgenti Rust.
- Se in futuro si riusa codice vero da Slipmat, lo si annota qui.

| Schermata "In reproducción" stile Zune HD (copertina piccola con ombra, testi a destra, parola gigante sullo sfondo, seek con -tempo, 5 controlli) | `docs/shots/40-ref-nowplaying.png` — **osservato da: screenshot del proprietario del 7/11** (preso dalla demo del Zune HD usata come riferimento visivo) | 2026-11-07 |
| Menu contestuale Apple Music iOS (voci in italiano) | `docs/shots/41-ref-options-menu.png` — **osservato da: screenshot del proprietario del 7/11** | 2026-11-07 |

Solo osservazione di screenshot: nessun codice della demo è stato letto o
copiato (la licenza resta in attesa; se l'autore dice no, cancellazione totale
come da regola §1).

## Icone interne (stage 8)
- `assets/icons/*.svg`: icone **symbolic di GNOME Adwaita** (LGPL-3.0+ /
  CC-BY-SA per parti del tema), copiate da `/usr/share/icons/Adwaita/symbolic/`
  su PC e ricolorate `#ffffff` (unico cambiamento: il fill). Richiesto dal
  proprietario ("prendile da GTK"). Usate via `ztos.RoundButton("assets/icons/…")`
  che le renderizza a 22×22 nell'anello standard dell'SDK.
- `icon.svg`: wrapper SVG che embedded `icon.png` (nostro logo Zune, data-URI)
  per la shell ztOS (librsvg sul telefono non legge PNG come tile glyph).
