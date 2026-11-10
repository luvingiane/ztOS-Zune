# INSTALL.md — installing on a ztOS phone

## The installer

From a computer that can reach the phone over ssh (a phone on the USB network
is usually `zerone@172.16.42.1`; your ssh key must be installed on it):

```sh
./install.sh                         # build and install the app (open it from the app list)
./install.sh --device user@host      # another phone or address
./install.sh --fix-phone             # also set up Qt for Python's compiled files (root password, once)
./install.sh --uninstall             # remove the app (Slipmat is not touched)
./install.sh --dry-run               # show what would happen, change nothing
```

What it does (no root needed):

1. Finds the ztOS SDK in `.sdk/ztos` or fetches it from the ztOS repository
   (sparse clone, only `sdk/` and `ztmetro/core`).
2. Checks the phone is reachable and shows what it has (`ztos-sdk doctor`:
   python, pyside6, Qt SVG, the ztMETRO shell). If Qt for Python's compiled
   files are missing, apps start about 2 s slower; `--fix-phone` creates them
   (the one step that needs the phone's root password, once).
3. Warns if `slipmatd` is not installed on the phone: the app needs Slipmat's
   daemon, signed in to Apple Music, or its pages stay empty.
4. Builds the app for aarch64 and copies the binary (the old one is kept as
   `<id>.before-<date>`), the icon and the `.desktop` entry, asks the shell to
   re-read the app list and checks that the binary on the phone is the one
   built here.

The app id is `dev.oneplus2.zunehd`, the name in the list is "Zune HD". The
manifest is [ztos.toml](ztos.toml). Only the app itself is changed on the
phone; the shared ztOS runtime is not touched.

Requirements on the phone: `python`, `pyside6`, `qt6-svg` (and the Qt Wayland
plugin) — check with `ztos-sdk doctor --device user@host`.

## Manual installation

Equivalent to the installer, using the SDK directly:

```sh
python3 .sdk/ztos/sdk/bin/ztos-sdk doctor --device user@host
python3 .sdk/ztos/sdk/bin/ztos-sdk deploy --device user@host    # installs the shared runtime too; may ask root's password once
python3 .sdk/ztos/sdk/bin/ztos-sdk logs   --device user@host -f # what the app printed
```

## Development on a computer

The SDK lives in `.sdk/ztos` (git-ignored) so nothing is written into your
ztOS clone:

```sh
python3 .sdk/ztos/sdk/bin/ztos-sdk run                  # 360x640 window (Esc = back)
python3 .sdk/ztos/sdk/bin/ztos-sdk run --shot out.png   # offscreen + screenshot after settling
ZTOS_GL=0 python3 .sdk/ztos/sdk/bin/ztos-sdk run        # no GPU layer on the computer
python3 .sdk/ztos/sdk/bin/ztos-sdk build                # dist/dev.oneplus2.zunehd (aarch64)
```

Developer switches (environment variables): `ZUNE_NAV=songs,now` opens inner
pages after the start (use with `ZTOS_SHOT_AFTER=6000` and `--shot`),
`ZUNE_SCROLL=1` scrolls by itself, `ZUNE_PERF=1` prints a `zune-perf` line per
second (see [PERF-ON-B.md](PERF-ON-B.md)), `ZUNE_NOIMG=1` loads no covers.

Tests (offscreen Qt, against a fake `slipmatd`; see the README):

```sh
env -i HOME=$HOME PATH=/usr/bin:/bin QT_QPA_PLATFORM=offscreen python3 -u tests/test_client.py
```

Note: with the environment of some harnesses PySide6 does not import; run
tests and the SDK through `env -i HOME=$HOME PATH=/usr/bin:/bin python3 …`.

## The native renderer

The aarch64 library (`sdk/native/prebuilt/aarch64/libztos-render.so`) is
prebuilt in the SDK with a matching hash, so `build` does not recompile it. To
rebuild it from scratch you need an aarch64 cross toolchain and a sysroot with
the GLES2 headers of the phone:

```sh
make -C .sdk/ztos/sdk/native ARCH=aarch64 FOREIGN= \
  CC="$TC/aarch64-none-linux-gnu-gcc --sysroot=$SR" \
  PKG_CONFIG_SYSROOT_DIR=$SR PKG_CONFIG_LIBDIR=$SR/usr/lib/pkgconfig:$SR/usr/share/pkgconfig
```
