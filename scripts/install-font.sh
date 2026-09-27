#!/bin/sh
# the menu icons are nerd font glyphs. this installs the symbols-only nerd font (about 2 MB, SIL OFL) so they
# show up: it only adds the icons and takes the letters from whatever font your terminal already uses, so it
# fits every theme. into ~/.local/share/fonts/paws, no root. `--dry-run` only says what it would do.
set -eu

URL="${PAWS_FONT_URL:-https://github.com/ryanoasis/nerd-fonts/releases/latest/download/NerdFontsSymbolsOnly.tar.xz}"
DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/paws"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

if command -v fc-list >/dev/null 2>&1 && fc-list 2>/dev/null | grep -qi "nerd font"; then
    echo "  font     a nerd font is already installed"
    exit 0
fi
if [ "$DRY" = 1 ]; then
    echo "  would download $URL"
    echo "  would install it into $DIR"
    exit 0
fi
for tool in curl tar; do
    command -v "$tool" >/dev/null 2>&1 || { echo "  note: $tool is missing, skipped the icon font (paws uses plain symbols)"; exit 0; }
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if curl -fsSL "$URL" -o "$tmp/font.tar.xz" && tar -xJf "$tmp/font.tar.xz" -C "$tmp" 2>/dev/null; then
    mkdir -p "$DIR"
    find "$tmp" \( -name 'SymbolsNerdFontMono-Regular.ttf' -o -name 'LICENSE*' -o -name 'OFL*' \) -type f -exec cp {} "$DIR" \;
    command -v fc-cache >/dev/null 2>&1 && fc-cache -f "$DIR" >/dev/null 2>&1
    echo "  font     installed the symbols font in $DIR (restart your terminal to see the icons)"
else
    echo "  note: couldn't fetch the icon font, paws uses plain symbols instead"
fi
