from __future__ import annotations

from textual.widgets import Static


class FooterHelp(Static):
    def __init__(self, text: str = "", **kwargs):
        super().__init__(text, **kwargs)
        self._shown = text

    def set_desc(self, desc: str, hints: str = ""):
        text = f"[b]{desc}[/b]" + (f"   [#9db0e0]{hints}[/]" if hints else "")
        if text != self._shown:
            self._shown = text
            self.update(text, layout=False)
