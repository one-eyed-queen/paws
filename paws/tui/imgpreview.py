from __future__ import annotations

import re
from pathlib import Path

from ..util import http

HOME = Path.home()
CACHE = HOME / ".cache/paws/img"


def fetch(url: str, timeout: int = 20) -> bytes | None:
    try:
        return http.get(url, timeout=timeout, headers={"Referer": "https://store.steampowered.com/"})
    except (OSError, ValueError):
        return None


def _cache_path(url):
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("?")[0])[:80] or "img"
    return CACHE / key


def cached_path(url: str) -> Path | None:
    if not url:
        return None
    p = _cache_path(url)
    if not p.exists():
        data = fetch(url)
        if not data:
            return None
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        except OSError:
            pass
    return p


def cached_build(url: str, width: int = 34) -> str | None:
    p = cached_path(url)
    return render(p, width) if p else None


def render(path: Path, width: int = 34) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(path).convert("RGB")
    except Exception:
        return None
    if image.width <= 1 or image.height <= 1:
        return None
    height = max(int(round(image.height / image.width * width * 0.5)), 1)
    image = image.resize((max(width, 1), max(height * 2, 2)), Image.Resampling.LANCZOS)
    px = image.load()

    out = []
    for y in range(0, image.height, 2):
        row = []
        for x in range(image.width):
            top = px[x, y]
            bot = px[x, min(y + 1, image.height - 1)]
            if top == bot:
                row.append(f"[#{top[0]:02x}{top[1]:02x}{top[2]:02x}]▀[/]")
            else:
                row.append(f"[#{bot[0]:02x}{bot[1]:02x}{bot[2]:02x} on #{top[0]:02x}{top[1]:02x}{top[2]:02x}]▀[/]")
        out.append("".join(row))
    return "\n".join(out)


def main():
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://cdn.cloudflare.steamstatic.com/steam/apps/730/header.jpg"
    from rich.console import Console

    Console().print(cached_build(url) or "no render")


if __name__ == "__main__":
    main()
