from __future__ import annotations

from functools import lru_cache

from ...paths import DATA_DIR

BG = DATA_DIR / "img" / "paws-bg.png"
NAVY = (10, 16, 32)
GLASS_TINT = (12, 20, 38)
PICTURE = 0.9
TINT = 0.62
BLUR = 0.605
GRAIN = 0.05


@lru_cache(maxsize=1)
def _source():
    from PIL import Image

    return Image.open(BG).convert("RGB")


@lru_cache(maxsize=2)
def _cropped(w, h):
    from PIL import Image, ImageEnhance

    src = _source()
    scale = max(w / src.width, h / src.height)
    big = src.resize(
        (max(w, round(src.width * scale)), max(h, round(src.height * scale))),
        Image.LANCZOS,
    )
    left, top = (big.width - w) // 2, (big.height - h) // 2
    image = big.crop((left, top, left + w, top + h))
    image = ImageEnhance.Brightness(image).enhance(1.1)
    image = ImageEnhance.Color(image).enhance(1.08)
    return Image.blend(Image.new("RGB", (w, h), NAVY), image, PICTURE)


@lru_cache(maxsize=2)
def compose(cols: int, rows: int, cell: tuple[int, int]):
    from PIL import Image, ImageFilter

    cw, ch = cell
    W, H = max(cols * cw, 16), max(rows * ch, 16)
    image = _cropped(W, H)
    small = image.resize((max(1, W // 4), max(1, H // 4)), Image.BILINEAR)
    blurred = small.filter(ImageFilter.GaussianBlur(max(1.0, ch * BLUR / 4))).resize((W, H), Image.BILINEAR)
    out = Image.blend(blurred, Image.new("RGB", (W, H), GLASS_TINT), TINT)
    noise = Image.effect_noise((W, H), 32).convert("RGB")
    return Image.blend(out, noise, GRAIN)
