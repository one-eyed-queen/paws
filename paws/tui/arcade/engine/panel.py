from __future__ import annotations

from rich.text import Text

from .palette import PAL


def label(name: str, value: object, width: int = 12) -> Text:
    t = Text(no_wrap=True)
    t.append(f"{name:<{width - 4}}", PAL["grey"])
    t.append(str(value), f"bold {PAL['white']}")
    return t
