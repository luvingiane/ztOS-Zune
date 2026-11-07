# ztos-zune-sdk — Zune HD per ztOS con l'SDK ufficiale

App musicale in stile Zune HD, fatta con l'SDK ztOS (`ztos`, Qt Widgets —
no QML) in `~/Github_Clones/ztos-zune-sdk`. È un client di `slipmatd`
(Slipmat, GPL-3.0-or-later): il demone non si tocca, si parla col suo socket
(vedi `IPC.md`, client in `slipmat/ipc.py` — riusato dal progetto QML).

- `main.py` — l'app (tappa 1: home hub Zune HD)
- `ztos.toml` — id `dev.oneplus2.zunehd`, name "Zune HD"
- `.sdk/ztos/` — copia locale dell'SDK (gitignorato): i comandi `ztos-sdk`
  girano su questa, il clone `~/Github_Clones/ztOS` non viene scritto
- `docs/shots/0x-*` — screenshot di riferimento (osservati guardando la demo
  live, vedi PROVENANCE.md); `docs/shots/30-*` — screenshot dell'app SDK
- `docs/compare/` — confronto affiancato demo-vs-app + tabelle
- `DESIGN.md`, `ACCEPTANCE.md`, `IPC.md`, `PROVENANCE.md`, `COPYING` —
  spec e regole (dal progetto precedente)
- `tests/compare.py` — confronto automatico 360×640

## Comandi

```sh
python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot docs/shots/30-home-sdk.png  # prova offscreen + shot
python3 .sdk/ztos/sdk/bin/ztos-sdk run                                     # finestra 360x640
python3 .sdk/ztos/sdk/bin/ztos-sdk build                                   # dist/dev.oneplus2.zunehd (aarch64)
env -i HOME=$HOME PATH=/usr/bin:/bin python3 tests/compare.py               # confronto
```

Vedi `INSTALL.md` per l'installazione manuale su B e `STATO.md` per lo stato.
