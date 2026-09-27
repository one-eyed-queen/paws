from __future__ import annotations

from textual.widgets import Static


class AsciiPanel(Static):
    def __init__(self, art_name: str | None = None, **kwargs):
        super().__init__(markup=True, **kwargs)
        self._art_name: str | None = None
        self._drawn: tuple | None = None
        if art_name:
            self.show(art_name)

    def pending(self, name: str, art=None):
        self._art_name = name
        self._art = art
        self._drawn = None

    def show(self, name: str | None = None, art=None) -> bool:
        from ... import art as art_module

        self._art_name = name or art_module.banner_name()
        self._art = art
        self._drawn = None
        return self._draw()

    def show_fitted(self, name: str, text: str, key: tuple):
        self._art_name = name
        self._drawn = key
        self.update(text)

    def _draw(self):
        from ... import art

        if not self._art_name:
            return False
        size = self.content_size
        if not size.width or not size.height:
            return True
        key = (self._art_name, size.width, size.height)
        if key == self._drawn:
            return True
        chosen = getattr(self, "_art", None)
        if chosen is None:
            arts = art.library()
            chosen = arts.get(self._art_name) or arts.get("placeholder.txt")
        if chosen is not None and chosen.lines:
            self.update("\n".join(art.display_fit(chosen, size.width, size.height)))
            self._drawn = key
            return True
        self.update("")
        self._drawn = key
        return False

    def on_mount(self):
        if self._art_name:
            self._draw()

    def on_resize(self, event):
        if self._art_name:
            self._draw()


class LogoBox(Static):
    def __init__(self, **kwargs):
        super().__init__("[#9db0e0]LOG O / IMG\n(drop art into\npaws/data/img/)[/]", **kwargs)
