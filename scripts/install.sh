#!/bin/sh
# paws installer, any linux. no root, nothing outside ur home.
#
#   git clone https://github.com/one-eyed-queen/paw && cd paw && ./scripts/install.sh
#
# makes a private python env in ~/.local/share/paws/venv, installs paws in it and links
# `paws` into ~/.local/bin. same on arch, debian, ubuntu, mint, pop, kali, parrot, fedora, opensuse,
# void, gentoo, steamos and friends (steamos / bazzite keep / read-only, this never touches it).
# keep the folder u cloned, `paws update` pulls new versions from it.
#
# options: --dry-run  --no-desktop  --no-alias  --no-font  --riced  --minimal  --prefix DIR  --bin DIR  --python PATH  --help
# the look: --riced is the full thing, --minimal is plain text and leaves out the pictures, art, mini games and pillow. it asks if you skip both.
set -eu

SRC=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/paws"
BIN="$HOME/.local/bin"
PYTHON=""
DRY=0
DESKTOP=1
ALIAS=1
FONT=1
TYPE="${PAWS_TYPE:-}"

say() { printf '%s\n' "$*"; }
die() { printf 'paws installer: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then say "  would run: $*"; else "$@"; fi; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        --no-desktop) DESKTOP=0 ;;
        --no-alias) ALIAS=0 ;;
        --no-font) FONT=0 ;;
        --riced) TYPE=riced ;;
        --minimal) TYPE=minimal ;;
        --prefix) shift; [ $# -gt 0 ] || die "--prefix needs a folder"; PREFIX="$1" ;;
        --bin) shift; [ $# -gt 0 ] || die "--bin needs a folder"; BIN="$1" ;;
        --python) shift; [ $# -gt 0 ] || die "--python needs a path"; PYTHON="$1" ;;
        -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

[ -f "$SRC/pyproject.toml" ] || die "run this from a paws checkout ($SRC has no pyproject.toml)"
[ "$(id -u)" -ne 0 ] || die "run it as your normal user, not root (paws lives in your home)"

# ---- a python that's new enough (3.9+) ----------------------------------------------------------
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; }

if [ -z "$PYTHON" ]; then
    for cand in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        if command -v "$cand" >/dev/null 2>&1 && py_ok "$cand"; then PYTHON=$(command -v "$cand"); break; fi
    done
fi
[ -n "$PYTHON" ] || die "need python 3.9 or newer. install one with your package manager (python3, or python3.11 on older distros)"
py_ok "$PYTHON" || die "$PYTHON is older than 3.9"

say "paws: installing from $SRC"
say "  python   $PYTHON ($("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])'))"
say "  into     $PREFIX/venv"
say "  command  $BIN/paws"

command -v git >/dev/null 2>&1 || say "  note: git isn't installed, so \`paws update\` won't work until it is"

if [ -z "$TYPE" ] && [ "$DRY" = 0 ] && ( : </dev/tty ) 2>/dev/null; then
    printf "  look: [r]iced (picture, banner, ascii art) or [m]inimal (plain text, in-app notifications only)? [r] " >/dev/tty
    read -r answer </dev/tty || answer=""
    case "$answer" in m* | M*) TYPE=minimal ;; esac
fi
[ -n "$TYPE" ] || TYPE=riced

# ---- the private environment ----------------------------------------------------------------------
VENV="$PREFIX/venv"
run mkdir -p "$PREFIX" "$BIN"
if [ "$DRY" = 0 ]; then
    if ! "$PYTHON" -m venv "$VENV" >/dev/null 2>&1; then
        rm -rf "$VENV"
        hint="install the venv module for your python"
        if command -v apt >/dev/null 2>&1; then hint="sudo apt install python3-venv (debian, ubuntu, mint, pop, kali, parrot)"; fi
        die "couldn't create a python environment. $hint, then run this again"
    fi
else
    say "  would run: $PYTHON -m venv $VENV"
fi

if [ "$TYPE" = riced ]; then SPEC="$SRC[riced]"; else SPEC="$SRC"; fi
run "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check "$SPEC"
if [ "$TYPE" = minimal ]; then (cd / && run "$VENV/bin/python" -m paws.riced prune); fi

run ln -sf "$VENV/bin/paws" "$BIN/paws"

# ---- desktop bits (nothing here opens a window) ---------------------------------------------------
if [ "$DESKTOP" = 1 ]; then run "$BIN/paws" desktop; fi
if [ "$ALIAS" = 1 ]; then run "$BIN/paws" alias --install; fi

if [ "$DRY" = 1 ]; then
    say "  would set the look to $TYPE"
else
    CONFIG="${PAWS_CONFIG_DIR:-$HOME/.config/paws}"
    if [ ! -e "$CONFIG/settings.json" ]; then
        mkdir -p "$CONFIG"
        printf '{\n  "type": "%s"\n}\n' "$TYPE" >"$CONFIG/settings.json"
    else
        "$BIN/paws" settings type "$TYPE" >/dev/null
    fi
    say "  look     $TYPE (change it any time in Settings > Type)"
fi

if [ "$FONT" = 1 ]; then
    if [ "$DRY" = 1 ]; then sh "$SRC/scripts/install-font.sh" --dry-run; else sh "$SRC/scripts/install-font.sh" || true; fi
fi

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "  note: $BIN isn't on this shell's PATH yet. open a new terminal (or run: $BIN/paws alias --install)" ;;
esac

if [ "$DRY" = 1 ]; then say "dry run: nothing was changed"; else say "done. run: paws"; fi
