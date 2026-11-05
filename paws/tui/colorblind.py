from __future__ import annotations

from functools import lru_cache

from rich.color import Color as RichColor
from rich.segment import Segment
from rich.style import Style
from textual.filter import LineFilter

from .. import settings

KINDS = ("protanopia", "deuteranopia", "tritanopia", "monochrome")
MODES = ("off", *KINDS)
PLACEHOLDER = "\U0010eeee"  # kitty image cells: their colour IS the image id, so it must never change

# machado et al. 2009, severity 1.0: what each kind of vision sees
_SEEN = {
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.01182, 0.04294, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.3039)),
}
# where the colour that vision loses gets moved to (fidaner's daltonize)
_RED_GREEN = ((0, 0, 0), (0.7, 1, 0), (0.7, 0, 1))
_BLUE_YELLOW = ((1, 0, 0.7), (0, 1, 0.7), (0, 0, 0))
_SHIFT = {"protanopia": _RED_GREEN, "deuteranopia": _RED_GREEN, "tritanopia": _BLUE_YELLOW}
_LUMA = (0.2126, 0.7152, 0.0722)

# minimal draws no colours of its own, so a mode there picks one clear text + background pair
MINIMAL_PAIRS = {
    "protanopia": ("#ffffff", "#0b2a5b"),
    "deuteranopia": ("#ffffff", "#0b2a5b"),
    "tritanopia": ("#ffffff", "#4a1020"),
    "monochrome": ("#ffffff", "#000000"),
}


def _luma(rgb) -> float:
    return sum(weight * channel for weight, channel in zip(_LUMA, rgb))


def mode() -> str:
    value = str(settings.get_setting("colorblind"))
    return value if value in MODES else "off"


def last_kind() -> str:
    """what the switch turns back on"""
    value = str(settings.get_setting("colorblind_kind"))
    return value if value in KINDS else "deuteranopia"


@lru_cache(maxsize=None)
def matrix(name: str) -> tuple[tuple[float, ...], ...] | None:
    if name == "monochrome":
        return (_LUMA, _LUMA, _LUMA)
    if name not in _SEEN:
        return None
    seen, shift = _SEEN[name], _SHIFT[name]
    lost = [[(i == j) - seen[i][j] for j in range(3)] for i in range(3)]
    moved = [[sum(shift[i][k] * lost[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return tuple(tuple((i == j) + moved[i][j] for j in range(3)) for i in range(3))


def convert(rgb: tuple[int, int, int], name: str) -> tuple[int, int, int]:
    m = matrix(name)
    if m is None:
        return rgb
    return tuple(max(0, min(255, round(sum(m[i][j] * rgb[j] for j in range(3))))) for i in range(3))


def image(picture, name: str | None = None):
    m = matrix(name or mode())
    if m is None:
        return picture
    flat = tuple(v for row in m for v in (*row, 0))
    alpha = picture.getchannel("A") if picture.mode in ("RGBA", "LA") else None
    out = picture.convert("RGB").convert("RGB", flat)
    if alpha is not None:
        out.putalpha(alpha)
    return out


class ColorBlindFilter(LineFilter):
    """every colour on the way to the terminal goes through here, so no widget has to know about it"""

    def __init__(self, name: str, minimal: bool):
        super().__init__()
        self.name = name
        self.minimal = minimal
        self._style = lru_cache(maxsize=4096)(self._convert)

    def _color(self, color):
        if color is None or color.is_default:
            return color
        return RichColor.from_rgb(*convert(tuple(color.get_truecolor()), self.name))

    def _text_color(self, color):
        """shifting a colour can darken it a lot (bright cyan under protanopia), so text keeps its brightness"""
        new = self._color(color)
        if color is None or color.is_default:
            return new
        before, after = _luma(color.get_truecolor()), _luma(new.get_truecolor())
        if after >= before or after == 0:
            return new
        scale = before / after
        return RichColor.from_rgb(*(min(255, round(c * scale)) for c in new.get_truecolor()))

    def _convert(self, style: Style) -> Style:
        if self.minimal:
            fg, bg = MINIMAL_PAIRS[self.name]
            return style + Style(color=fg, bgcolor=bg)
        return style + Style(color=self._text_color(style.color), bgcolor=self._color(style.bgcolor))

    def apply(self, segments, background):
        out = []
        for segment in segments:
            if segment.style is None and not self.minimal:
                out.append(segment)
            elif segment.text.startswith(PLACEHOLDER):
                out.append(segment)
            else:
                out.append(Segment(segment.text, self._style(segment.style or Style()), segment.control))
        return out


def filter_for(minimal: bool) -> ColorBlindFilter | None:
    name = mode()
    return None if name == "off" else ColorBlindFilter(name, minimal)
