# INSTALL.md — installazione manuale su B (utente `zerone`, senza root)

Il binario è già pronto: `dist/dev.oneplus2.zunehd` (ELF aarch64 + archivio
zip con app, runtime `ztos`, zygote e la libreria nativa
`lib/ztos/_native_renderer.so` prebuilt aarch64). **Questi passi NON sono stati
eseguiti**: li esegue il proprietario (o chi ha il suo ok) sul telefono.

```sh
# sul PC: copia i binari sul telefono (rete USB 172.16.42.1)
# (dev.oneplus2.zuneref = app minima di rif. per le misure perf, vedi PERF-ON-B.md)
scp dist/dev.oneplus2.zunehd ref/dist/dev.oneplus2.zuneref <user>@<phone-ip>:~/.local/share/ztos/apps/
# oppure via ssh:
ssh <user>@<phone-ip> 'mkdir -p ~/.local/share/ztos/apps ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps'
ssh <user>@<phone-ip> 'cat > ~/.local/share/ztos/apps/dev.oneplus2.zunehd' < dist/dev.oneplus2.zunehd
ssh <user>@<phone-ip> 'cat > ~/.local/share/ztos/apps/dev.oneplus2.zuneref' < ref/dist/dev.oneplus2.zuneref
chmod +x sul telefono: ssh <user>@<phone-ip> 'chmod 755 ~/.local/share/ztos/apps/dev.oneplus2.zunehd ~/.local/share/ztos/apps/dev.oneplus2.zuneref'

# icona e .desktop (sul telefono):
ssh <user>@<phone-ip> 'cat > ~/.local/share/icons/hicolor/scalable/apps/dev.oneplus2.zunehd.svg' < icon.svg
ssh <user>@<phone-ip> 'cat > ~/.local/share/applications/dev.oneplus2.zunehd.desktop' <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Zune HD
Comment=Zune HD style music player, a Slipmat (slipmatd) client
Exec=/home/zerone/.local/share/ztos/apps/dev.oneplus2.zunehd
Icon=dev.oneplus2.zunehd
Terminal=false
StartupWMClass=ztos.dev.oneplus2.zunehd
Categories=Audio;Music;
X-ZtOS-Id=dev.oneplus2.zunehd
X-ZtOS-Version=0.1.0
DESKTOP
# fa rileggere la lista app alla shell:
printf 'apps\n' > "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ztmetro.ctl"   # su B dentro ztOS

# .desktop + icona dell'app di riferimento (zuneref):
ssh <user>@<phone-ip> 'cat > ~/.local/share/icons/hicolor/scalable/apps/dev.oneplus2.zuneref.svg' < ref/icon.svg
ssh <user>@<phone-ip> 'cat > ~/.local/share/applications/dev.oneplus2.zuneref.desktop' <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Zune Ref
Comment=Minimal SDK reference app for perf comparison
Exec=/home/zerone/.local/share/ztos/apps/dev.oneplus2.zuneref
Icon=dev.oneplus2.zuneref
Terminal=false
StartupWMClass=ztos.dev.oneplus2.zuneref
Categories=Audio;Music;
X-ZtOS-Id=dev.oneplus2.zuneref
X-ZtOS-Version=0.1.0
DESKTOP
```

## Misure di prestazioni su B (ZUNE_PERF=1)

Le app scrivono una riga `zune-perf` al secondo su stderr → nel log
`~/.local/state/ztos/<id>.log`. I comandi esatti per avvio instrumentato,
raccolta log e la tabella da compilare sono in **PERF-ON-B.md** (solo il
proprietario li esegue su B). In breve: dentro la sessione ztOS,
`ZUNE_PERF=1 ~/.local/share/ztos/apps/dev.oneplus2.zunehd` (e `.zuneref`),
poi `cat ~/.local/state/ztos/dev.oneplus2.zunehd.log`.

Requisiti su B (già presenti): `python`, `pyside6`, `qt6-wayland`, `qt6-svg`
(verifica: `ztos-sdk doctor` dal PC, oppure `pacman -Q pyside6 qt6-wayland qt6-svg`).

## Rigenerare il binario (sul PC, senza toccare il clone ztOS)

L'SDK è copiato in locale in `.sdk/ztos/` (gitignorato) proprio per non
scrivere in `~/Github_Clones/ztOS`:

```sh
cd ~/Github_Clones/ztos-zune-sdk
python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot docs/shots/30-home-sdk.png   # prova + screenshot offscreen
# schermate interne (dev-only, ZUNE_NAV):
ZTOS_SHOT_AFTER=6000 ZUNE_NAV=music,songs python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot docs/shots/31-music-songs.png
ZUNE_PERF=1 ZTOS_SHOT_AFTER=9000 ZUNE_NAV=music,songs ZUNE_SCROLL=1 \
  python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot /tmp/x.png                  # log zune-perf con scroll simulato
python3 .sdk/ztos/sdk/bin/ztos-sdk build                                     # -> dist/dev.oneplus2.zunehd
(cd ref && python3 ../.sdk/ztos/sdk/bin/ztos-sdk build)                      # -> ref/dist/dev.oneplus2.zuneref
env -i HOME=$HOME PATH=/usr/bin:/bin python3 tests/compare.py                # confronto affiancato (soglie in ACCEPTANCE.md)
env -i HOME=$HOME PATH=/usr/bin:/bin python3 tests/test_client.py             # test client vs slipmatd finto (fixture anonimizzate in tests/fixtures/)
env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_player.py   # geometria Player (area utile 28/40) + menu Opzioni su socket finto
env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 tests/test_art.py      # fetcher artwork: download reale via HTTP locale + cache
# screenshot Now Playing / menu Opzioni:
ZTOS_SHOT_AFTER=6000 ZUNE_NAV=now     python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot docs/shots/40-now-sdk.png
ZTOS_SHOT_AFTER=6000 ZUNE_NAV=options python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot docs/shots/41-options-sdk.png
```

La libreria nativa aarch64 (`sdk/native/prebuilt/aarch64/libztos-render.so`)
è **prebuilt con hash valido**, quindi `build` non la ricompila. Se serve
ricompilarla da zero (toolchain e sysroot di B in `~/oneplus2/build`):

```sh
TC=~/oneplus2/build/toolchain/arm-gnu-toolchain-14.2.rel1-x86_64-aarch64-none-linux-gnu/bin
SR=~/oneplus2/build/sysroot-b
make -C .sdk/ztos/sdk/native ARCH=aarch64 FOREIGN= \
  CC="$TC/aarch64-none-linux-gnu-gcc --sysroot=$SR" \
  PKG_CONFIG_SYSROOT_DIR=$SR PKG_CONFIG_LIBDIR=$SR/usr/lib/pkgconfig:$SR/usr/share/pkgconfig
# (come scripts/cross-ztos.sh; le intestazioni GLES2 vengono dal sysroot-b)
```

## Sviluppo sul PC

```sh
python3 .sdk/ztos/sdk/bin/ztos-sdk run                 # finestra 360x640 (Esc = indietro)
python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot out.png  # offscreen + screenshot dopo il settle
ZTOS_GL=0 python3 .sdk/ztos/sdk/bin/ztos-sdk run       # niente GPU layer sul PC
env -i HOME=$HOME PATH=/usr/bin:/bin python3 tests/compare.py   # confronto affiancato
```

Nota ambiente PC T3: con l'`LD_LIBRARY_PATH` dell'harness PySide6 non importa;
usare `env -i HOME=$HOME PATH=/usr/bin:/bin python3 ...`.
