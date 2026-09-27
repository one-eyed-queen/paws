from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from ... import settings
from .gradient import tween

TRACK = "#1a2238"
IDLE_TRACK = "#2b2f38"
IDLE_TEXT = "#8b93a5"
DARK_TEXT = "#06101f"
LIGHT_TEXT = "#dbe4ff"
IDLE_LABEL = "~UwU~"


class JobBar(Widget):
    """shows what paws is busy with, read from app.job so it's the same on every screen. riced: a bar that fills
    from the left with the words and percent on it, rainbow coloured, dark grey with ~UwU~ when nothing is going on.
    minimal: only there during a job, at the bottom: the words and percent, then solid blocks growing from the left
    (no track, so an empty bar is not a line)"""

    DEFAULT_CSS = """
    JobBar { height: 2; margin: 1 2 0 2; }
    JobBar.thin { height: 1; margin: 0 1; }
    """

    def on_mount(self):
        self.set_interval(0.1, self._tick)
        self._tick()

    def _busy(self):
        return self.app.job.shown()

    def _tick(self):
        self.display = self._busy() or not settings.is_minimal()
        if self.display:
            self.refresh()

    def render(self):
        job = self.app.job
        width = max(self.size.width, 1)
        busy = self._busy()
        percent = f"{round(job.value() * 100)}%"
        words = f"{job.label}  {percent}" if busy else IDLE_LABEL
        if settings.is_minimal():
            if not busy:
                return Text("")
            return Text(f"{words}\n" + "█" * round(width * job.value()), no_wrap=True)
        return self._thick(width, words, job.value() if busy else None)

    def _thick(self, width, words, value):
        rows = max(self.size.height, 1)
        filled = 0 if value is None else round(width * value)
        label = f" {words} "
        left = max((width - len(label)) // 2, 0)
        out = Text(no_wrap=True)
        for row in range(rows):
            for x in range(width):
                char = label[x - left] if row == rows // 2 and left <= x < left + len(label) else " "
                if value is None:
                    style = f"bold {IDLE_TEXT} on {IDLE_TRACK}"
                elif x < filled:
                    style = f"bold {DARK_TEXT} on {tween(x / max(width - 1, 1))}"
                else:
                    style = f"bold {LIGHT_TEXT} on {TRACK}"
                out.append(char, style=style)
            if row < rows - 1:
                out.append("\n")
        return out
