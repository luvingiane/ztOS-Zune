# PROVENANCE.md — where things come from

## 1. Visual reference and its license status

- Visual reference: `https://github.com/bransonwerner/zune-player` (live demo
  `https://bransonwerner.github.io/zune-player/`), the Zune HD web demo where
  the design of this app started.
- **That repository has no license.** The owner opened an issue asking the
  author for a permissive license (MIT/Apache-2.0 or GPL-3.0-or-later) and for
  permission to redo the interface in Qt. **Answer pending.**
- Until the owner records in writing that the author granted a license, **none
  of its code is read, copied or adapted** (no TS, CSS, HTML or assets).

> **Public repository:** the screenshots and measurements taken from the demo,
> and the tooling that compared the app against them, are **not published**.
> They exist only in the owner's local history. The app contains no sample
> data of any kind.

## 2. What was observed (and when)

Only the **running demo** was looked at (screenshots, timing and position
measurements) and those observations were used as a specification. Nothing was
ever copied from its source.

| What | Observed from | Date |
|---|---|---|
| Home screen, "music" panorama hub, song list, default screen | screenshots of the running demo | 2026-11-07 |
| Geometry, fonts, colors, animation durations and curves | DOM measurements of the running demo in a browser tab | 2026-11-07 |
| "Now playing" in the Zune HD style, options menu | screenshots supplied by the owner | 2026-11-07 |

On 2026-11-07 (~17:55) live observation **stopped**: the browser tab was
closed and no URL of `bransonwerner/zune-player` has been opened since.
Everything not covered by those measurements is **original work** inspired by
general knowledge of the Zune HD interface.

## 3. What was never done

- No file of the `bransonwerner/zune-player` repository was read, downloaded,
  copied or adapted (no TS/CSS/HTML/assets), neither through a browser nor
  through git, and no network asset beyond the demo page itself was opened.
- No Microsoft font, image or code is in this repository. The one exception is
  `icon.png`, the Zune logo, a Microsoft trademark: it is kept knowingly by the
  owner, the product being discontinued.
- Fonts: the ztOS system fonts are used (stack "Segoe UI" / "Selawik" /
  "Open Sans" / sans-serif as in the ztOS wrapper, falling back to DejaVu Sans
  on a PC).
- Icons: GNOME Adwaita symbolic icons (see §6).

## 4. If the author refuses

Everything derived from the demo is removed from the project: screenshots,
recordings, measurement tables, anything built by looking at it, and every
reference in the commit history (the repository is recreated without it if
needed). Then `grep -ri "zune-player\|bransonwerner" .` must return nothing and
the outcome is recorded. The project is not redesigned "from a distance": it
closes. This file is deleted last.

## 5. Code reused from Slipmat (GPL-3.0-or-later)

- `COPYING` is the GPL-3 text, copied verbatim from Slipmat 0.12.0 (license
  text, not code).
- The protocol in `IPC.md` is **documentation** of `crates/slipmat-core/src/ipc.rs`
  (GPL-3.0-or-later), re-read and cited with file and line. The Python client
  (`slipmat/ipc.py`) reimplements it (newline-delimited JSON on the same
  socket) and copies no Rust source.
- If real Slipmat code is ever reused, it is recorded here.

## 6. Icons

- `assets/icons/*.svg`: **GNOME Adwaita symbolic icons** (LGPL-3.0+, with
  CC-BY-SA for parts of the theme), copied from
  `/usr/share/icons/Adwaita/symbolic/` and recolored `#ffffff` (the fill is the
  only change). They are used through `ztos.RoundButton("assets/icons/…")`,
  which renders them at 22×22 inside the SDK's standard ring.
- `icon.png`: `zune.png`, supplied verbatim by the owner (1280×1181 RGBA, pink
  and orange Zune logo on white, sha256 af9b0b6a…), used unmodified as the app
  icon (`ztos.toml`); ztmetro derives the white glyph from it.
