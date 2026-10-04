#!/usr/bin/env sh
# paws - single-command install, any distro.
#
# Run:
#   curl -fsSL https://raw.githubusercontent.com/one-eyed-queen/paws/main/scripts/paws-install.sh | bash
#
# Picks the best install method for the machine it's run on: a real pacman
# package (built with makepkg) on Arch and family, or the universal no-root
# python+venv installer (scripts/install.sh) everywhere else. Either way you
# get the paws command, the .desktop launcher and the icon.
#
# Pick the look with --riced (background picture, banner, ascii art) or
# --minimal (plain text, lines and boxes). Without either it asks when it can.
# You can change it later in paws: Settings > Type.
set -eu

BASE_URL="${PAWS_URL:-https://github.com/one-eyed-queen/paws/releases/download/v1.0.127}"
VER="1.0.127"

if [ "$(id -u)" -eq 0 ]; then
    echo "paws-install: run as a normal user." >&2
    exit 1
fi

TYPE="${PAWS_TYPE:-}"
FONT=1
for arg in "$@"; do
    case "$arg" in
        --riced) TYPE=riced ;;
        --minimal) TYPE=minimal ;;
        --no-font) FONT=0 ;;
        *) echo "paws-install: unknown option $arg (use --riced, --minimal or --no-font)" >&2; exit 1 ;;
    esac
done

if [ -z "$TYPE" ] && ( : </dev/tty ) 2>/dev/null; then
    printf "Look: [r]iced (picture, banner, ascii art) or [m]inimal (plain text, boxes)? [r] " >/dev/tty
    read -r answer </dev/tty || answer=""
    case "$answer" in m* | M*) TYPE=minimal ;; esac
fi
[ -n "$TYPE" ] || TYPE=riced

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch() {
    echo "==> downloading paws $VER"
    curl -fsSL "$BASE_URL/paws-$VER.tar.gz" -o "$TMP/paws-$VER.tar.gz"
    tar -xzf "$TMP/paws-$VER.tar.gz" -C "$TMP"
}

install_pacman() {
    fetch
    cd "$TMP/paws-$VER"
    echo "==> building the pacman package"
    makepkg --noconfirm
    echo "==> installing"
    sudo pacman -U --noconfirm ./*.pkg.tar.zst
}

install_universal() {
    fetch
    echo "==> installing (python + venv, no root)"
    if [ "$FONT" = 1 ]; then
        sh "$TMP/paws-$VER/scripts/install.sh" "--$TYPE"
    else
        sh "$TMP/paws-$VER/scripts/install.sh" "--$TYPE" --no-font
    fi
}

if [ "$TYPE" = riced ] && command -v pacman >/dev/null 2>&1 && command -v makepkg >/dev/null 2>&1; then
    install_pacman
else
    install_universal
fi

if [ "$FONT" = 1 ] && [ -f "$TMP/paws-$VER/scripts/install-font.sh" ]; then
    sh "$TMP/paws-$VER/scripts/install-font.sh" || true
fi

CONFIG="${PAWS_CONFIG_DIR:-$HOME/.config/paws}"
if [ ! -e "$CONFIG/settings.json" ]; then
    mkdir -p "$CONFIG"
    printf '{\n  "type": "%s"\n}\n' "$TYPE" >"$CONFIG/settings.json"
elif command -v paws >/dev/null 2>&1; then
    paws settings type "$TYPE" >/dev/null
fi

echo
echo "Done (look: $TYPE). Open paws from any terminal:"
echo "    paws"
echo "Or from your app menu (titled 'paws')."
