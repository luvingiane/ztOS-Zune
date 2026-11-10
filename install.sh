#!/usr/bin/env bash
# ztOS-Zune installer: builds the app and installs it on a ztOS phone over ssh.
#
#   ./install.sh                         # phone at the SDK default (zerone@172.16.42.1, USB network)
#   ./install.sh --device user@host      # another phone / address
#   ./install.sh --no-launch             # install without opening the app
#   ./install.sh --uninstall             # take the app off the phone
#   ./install.sh --dry-run               # print what would happen, change nothing
#   ./install.sh --fix-phone             # also set up Qt for Python's compiled files (asks root's password once)
#
# It uses the official ztOS SDK (`ztos-sdk`). If the SDK is not found it is
# fetched from the ztOS repository into ./.sdk (git-ignored). Nothing is
# changed on the phone except the app itself (binary, .desktop entry, icon).
# No root is needed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZTOS_REPO="${ZTOS_REPO:-https://github.com/Zerone-Laboratories/ztOS}"
DEVICE="${ZTOS_DEVICE:-zerone@172.16.42.1}"
SDK_DIR="${ZTOS_SDK_DIR:-$HERE/.sdk/ztos}"
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR"
ACTION=install
DRY=0
FIX=0

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else "$@"; fi; }

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --device)    DEVICE="${2:?--device needs user@host}"; shift 2 ;;
    --no-launch) shift ;;   # kept for compatibility: the app is never launched from here
    --fix-phone) FIX=1; shift ;;
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
  ssh $SSH_OPTS -o ConnectTimeout=5 "$DEVICE" true 2>/dev/null \
    || die "cannot ssh to $DEVICE without a password prompt. Check the address (a phone on the USB network is usually zerone@172.16.42.1) and that your ssh key is installed on it."
fi

if [ "$ACTION" = uninstall ]; then
  say "removing the app from the phone"
  run "${SDK[@]}" uninstall -C "$HERE" --device "$DEVICE"
  say "done (Slipmat and its data are not touched)"
  exit 0
fi

# 3. what the phone has (informational: nothing here needs root) -------------------
say "checking the phone"
if ! run "${SDK[@]}" doctor --device "$DEVICE"; then
  warn "the list above shows what the phone lacks. The app installs anyway."
  warn "If only \"Qt for Python compiled\" is missing, apps start ~2 s slower; ./install.sh --fix-phone sets it up (needs root's password, once)."
fi
if [ "$FIX" = 1 ]; then
  say "setting up the phone (asks for root's password on the phone)"
  run "${SDK[@]}" doctor --fix --device "$DEVICE"
fi

# 4. the Slipmat daemon: this app is only its touch interface -------------------
if [ "$DRY" = 0 ]; then
  if ! ssh $SSH_OPTS "$DEVICE" 'command -v slipmatd >/dev/null' 2>/dev/null; then
    warn "slipmatd (the Slipmat daemon) is not installed on the phone."
    warn "The app will install and start, but its pages stay empty until slipmatd is there and signed in."
    warn "Slipmat: https://github.com/SoftARV/Slipmat"
  fi
fi

# 5. build ---------------------------------------------------------------------
APP_ID="$(sed -n 's/^id *= *"\([^"]*\)".*/\1/p' "$HERE/ztos.toml" | head -1)"
APP_NAME="$(sed -n 's/^name *= *"\([^"]*\)".*/\1/p' "$HERE/ztos.toml" | head -1)"
APP_VER="$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' "$HERE/ztos.toml" | head -1)"
APP_DESC="$(sed -n 's/^description *= *"\([^"]*\)".*/\1/p' "$HERE/ztos.toml" | head -1)"
BIN="$HERE/dist/$APP_ID"
say "building $APP_NAME $APP_VER for aarch64"
run "${SDK[@]}" build -C "$HERE"

# 6. install: binary, icon, menu entry (the same files the SDK would put there) ----
say "installing on $DEVICE (the old binary is kept as $APP_ID.before-<date>)"
if [ "$DRY" = 1 ]; then
  printf '  [dry-run] copy %s, icon.png and a .desktop entry to the phone, then refresh the app list\n' "$BIN"
else
  STAMP="$(date +%Y%m%d-%H%M)"
  PHONE_HOME="$(ssh $SSH_OPTS "$DEVICE" 'echo "$HOME"')"
  ssh $SSH_OPTS "$DEVICE" 'mkdir -p ~/.local/share/ztos/apps ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps'
  ssh $SSH_OPTS "$DEVICE" "[ -f ~/.local/share/ztos/apps/$APP_ID ] && cp -p ~/.local/share/ztos/apps/$APP_ID ~/.local/share/ztos/apps/$APP_ID.before-$STAMP || true"
  # copy to a temporary name and rename: a running copy of the app keeps working
  ssh $SSH_OPTS "$DEVICE" "cat > ~/.local/share/ztos/apps/$APP_ID.new && chmod 755 ~/.local/share/ztos/apps/$APP_ID.new && mv -f ~/.local/share/ztos/apps/$APP_ID.new ~/.local/share/ztos/apps/$APP_ID" < "$BIN"
  ssh $SSH_OPTS "$DEVICE" "cat > ~/.local/share/icons/hicolor/256x256/apps/$APP_ID.png" < "$HERE/icon.png"
  ssh $SSH_OPTS "$DEVICE" "cat > ~/.local/share/applications/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=$APP_DESC
Exec=$PHONE_HOME/.local/share/ztos/apps/$APP_ID
Icon=$APP_ID
Terminal=false
StartupWMClass=ztos.$APP_ID
Categories=Audio;Music;
X-ZtOS-Id=$APP_ID
X-ZtOS-Version=$APP_VER
DESKTOP
  # refresh the shell's app list
  ssh $SSH_OPTS "$DEVICE" 'c="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ztmetro.ctl"; [ -p "$c" ] && timeout 2 sh -c '"'"'printf "apps\n" > "$1"'"'"' _ "$c" || true'
  local_hash="$(sha256sum "$BIN" | cut -c1-16)"
  phone_hash="$(ssh $SSH_OPTS "$DEVICE" "sha256sum ~/.local/share/ztos/apps/$APP_ID | cut -c1-16")"
  [ "$local_hash" = "$phone_hash" ] || die "the binary on the phone differs from the one built here ($phone_hash vs $local_hash)"
  say "checked: same binary on both sides ($local_hash)"
fi

say "done. Open \"$APP_NAME\" from the app list; in its Settings page choose \"sign in\" if slipmatd is not signed in yet."
