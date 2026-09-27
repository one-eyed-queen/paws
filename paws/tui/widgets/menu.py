from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import ListItem, ListView

from .gradient import tween
from .icons import icon


class MenuItem(ListItem):
    def __init__(
        self,
        key: str,
        label: str,
        desc: str,
        icon_name: str = "go",
        disabled: bool = False,
        hue: float | None = None,
        hint: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.disabled = disabled
        self.data = key
        self.desc = desc
        self.title = label
        self._icon_name, self._hue = icon_name, hue
        self._hint = hint
        self.text = self._markup(label)

    def _markup(self, label):
        glyph = f"{icon(self._icon_name)}  {label}"
        if self.disabled:
            return f"[dim s]{glyph}[/dim s]"
        if self._hue is not None:
            return f"[{tween(self._hue)}]{glyph}[/]"
        return glyph

    @property
    def hint_text(self) -> str:
        return Text.from_markup(self._hint).plain if self._hint else ""

    def relabel(self, label: str):
        self.title = label
        self.text = self._markup(label)
        self.refresh(layout=False)

    def set_hint(self, text: str):
        if text != self._hint:
            self._hint = text
            self.refresh(layout=False)

    def _compact(self):
        return any(a.has_class("-compact") for a in self.ancestors)

    def render(self) -> Text:
        left = Text.from_markup(self.text, overflow="ellipsis")
        left.no_wrap = True
        width = self.content_size.width
        if not self._hint or width <= 0 or self._compact():
            return left
        colour = "#dbe4ff" if self.has_class("-highlight") else "#9db0e0"
        right = Text.from_markup(f"[{colour}]{self._hint}[/]")
        gap = width - left.cell_len - right.cell_len
        if gap < 2:
            return left
        out = left + Text(" " * gap) + right
        out.no_wrap = True
        out.overflow = "ellipsis"
        return out


class Menu(ListView):
    index = reactive[Optional[int]](None, init=False, repaint=False)


def restore_index(menu: ListView, index: int | None):
    clamped = 0 if index is None or index < 0 else min(index, len(menu.children) - 1)
    if menu.index != clamped:
        menu.index = clamped
        return
    if menu.index is None or not menu.children:
        return
    for i, child in enumerate(menu.children):
        child.highlighted = i == clamped
    menu.scroll_to_widget(menu.children[clamped], animate=False)
