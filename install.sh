#!/usr/bin/env bash
# ztOS-Zune installer: builds the app and installs it on a ztOS phone over ssh.
#
#   ./install.sh                         # phone at the SDK default (zerone@172.16.42.1, USB network)
#   ./install.sh --device user@host      # another phone / address
#   ./install.sh --no-launch             # install without opening the app
#   ./install.sh --uninstall             # take the app off the phone
#   ./install.sh --dry-run               # print what would happen, change nothing
#
# It uses the official ztOS SDK (`ztos-sdk`). If the SDK is not found it is
# fetched from the ztOS repository into ./.sdk (git-ignored). Nothing is
# changed on the phone except the app itself (binary, .desktop entry, icon).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZTOS_REPO="${ZTOS_REPO:-https://github.com/Zerone-Laboratories/ztOS}"
DEVICE="${ZTOS_DEVICE:-zerone@172.16.42.1}"
SDK_DIR="${ZTOS_SDK_DIR:-$HERE/.sdk/ztos}"
ACTION=deploy
DRY=0

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else "$@"; fi; }

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --device)    DEVICE="${2:?--device needs user@host}"; shift 2 ;;
    --no-launch) ACTION=install; shift ;;
    --uninstall) ACTION=uninstall; shift ;;
    --dry-run)   DRY=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

command -v python3 >/dev/null || die "python3 is required on this computer"
command -v ssh     >/dev/null || die "ssh is required on this computer"

# 1. the SDK ---------------------------------------------------------------
SDK_BIN="$SDK_DIR/sdk/bin/ztos-sdk"
if [ ! -f "$SDK_BIN" ]; then
  command -v git >/dev/null || die "git is required to fetch the ztOS SDK (or set ZTOS_SDK_DIR to an existing copy)"
  say "fetching the ztOS SDK from $ZTOS_REPO"
  if [ "$DRY" = 1 ]; then
    printf '  [dry-run] sparse clone of %s (sdk/, ztmetro/core) into %s\n' "$ZTOS_REPO" "$SDK_DIR"
  else
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    git clone --quiet --depth 1 --filter=blob:none --sparse "$ZTOS_REPO" "$tmp/ztOS"
    git -C "$tmp/ztOS" sparse-checkout set sdk ztmetro/core
    mkdir -p "$SDK_DIR/ztmetro"
    cp -r "$tmp/ztOS/sdk" "$SDK_DIR/sdk"
    cp -r "$tmp/ztOS/ztmetro/core" "$SDK_DIR/ztmetro/core"
  fi
fi
SDK=(python3 "$SDK_BIN")

# 2. the phone ---------------------------------------------------------------
say "phone: $DEVICE"
if [ "$DRY" = 0 ]; then
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$DEVICE" true 2>/dev/null \
    || die "cannot ssh to $DEVICE without a password prompt. Check the address (a phone on the USB network is usually zerone@172.16.42.1) and that your ssh key is installed on it."
fi

if [ "$ACTION" = uninstall ]; then
  say "removing the app from the phone"
  run "${SDK[@]}" uninstall -C "$HERE" --device "$DEVICE"
  say "done (Slipmat and its data are not touched)"
  exit 0
fi

# 3. the phone has what the app needs ------------------------------------------
say "checking the phone (python, pyside6, Qt, ztMETRO shell)"
if ! run "${SDK[@]}" doctor --device "$DEVICE"; then
  warn "the phone is missing something the SDK can set up (usually Qt for Python's compiled files)."
  warn "The next step does it, once, and asks for the phone's root password (su): run this installer"
  warn "in a terminal, or export ZTOS_ROOT_PASSWORD. Nothing is changed on the phone before that."
  if [ "$DRY" = 0 ] && [ ! -t 0 ] && [ -z "${ZTOS_ROOT_PASSWORD:-}" ]; then
    die "no terminal to ask the root password on. Re-run ./install.sh from a terminal."
  fi
fi

# 4. the Slipmat daemon: this app is only its touch interface -------------------
if [ "$DRY" = 0 ]; then
  if ! ssh -o BatchMode=yes "$DEVICE" 'command -v slipmatd >/dev/null' 2>/dev/null; then
    warn "slipmatd (the Slipmat daemon) is not installed on the phone."
    warn "The app will install and start, but its pages stay empty until slipmatd is there and signed in."
    warn "Slipmat: https://github.com/SoftARV/Slipmat"
  fi
fi

# 5. build + install (+ open) -----------------------------------------------------
say "building and installing (this compiles the app for aarch64)"
if [ "$ACTION" = deploy ]; then
  run "${SDK[@]}" deploy -C "$HERE" --device "$DEVICE"
else
  run "${SDK[@]}" install -C "$HERE" --device "$DEVICE"
fi

say "installed. Open \"Zune HD\" from the app list; in its Settings page choose \"sign in\" if slipmatd is not signed in yet."
