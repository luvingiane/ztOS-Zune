# INSTALL.md — installazione manuale su B (utente `zerone`, senza root)

Il binario è già pronto: `dist/dev.oneplus2.zunehd` (ELF aarch64 + archivio
zip con app, runtime `ztos`, zygote e la libreria nativa
`lib/ztos/_native_renderer.so` prebuilt aarch64). **Questi passi NON sono stati
eseguiti**: li esegue il proprietario (o chi ha il suo ok) sul telefono.

```sh
# sul PC: copia il binario sul telefono (rete USB 172.16.42.1)
scp dist/dev.oneplus2.zunehd <user>@<phone-ip>:~/.local/share/ztos/apps/dev.oneplus2.zunehd
# oppure via ssh:
ssh <user>@<phone-ip> 'mkdir -p ~/.local/share/ztos/apps ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps'
ssh <user>@<phone-ip> 'cat > ~/.local/share/ztos/apps/dev.oneplus2.zunehd' < dist/dev.oneplus2.zunehd
chmod +x sul telefono: ssh <user>@<phone-ip> 'chmod 755 ~/.local/share/ztos/apps/dev.oneplus2.zunehd'

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
```

Requisiti su B (già presenti): `python`, `pyside6`, `qt6-wayland`, `qt6-svg`
(verifica: `ztos-sdk doctor` dal PC, oppure `pacman -Q pyside6 qt6-wayland qt6-svg`).

## Rigenerare il binario (sul PC, senza toccare il clone ztOS)

L'SDK è copiato in locale in `.sdk/ztos/` (gitignorato) proprio per non
scrivere in `~/Github_Clones/ztOS`:

```sh
cd ~/Github_Clones/ztos-zune-sdk
python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot docs/shots/30-home-sdk.png   # prova + screenshot offscreen
python3 .sdk/ztos/sdk/bin/ztos-sdk build                                     # -> dist/dev.oneplus2.zunehd
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
