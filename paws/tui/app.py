from __future__ import annotations

import asyncio
import re
import time

from textual import events
from textual.app import App
from textual.filter import NoColor
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Input, TextArea

from .. import drop
from .. import notify
from .. import settings
from .. import textdrop
from .jobs import Job
from .screens import HomeScreen
from .screens.drop import DropScreen
from .underlay import Underlay
from .widgets import (
    backdrop,
    hires,
)

PAWS_THEME = Theme(
    name="paws",
    primary="#4066ff",
    secondary="#9b4dff",
    accent="#00d0ff",
    warning="#ffb84d",
    error="#ff4da6",
    success="#3ddc97",
    foreground="#dbe4ff",
    background="#0a1020",
    surface="#101a30",
    panel="#0c1424",
    dark=True,
)


class PawApp(App):
    TITLE = "paws"
    SUB_TITLE = "SLSsteam manager"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "quit"),
        Binding("ctrl+d", "drop_zone", "drop files", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_theme(PAWS_THEME)
        self.job = Job()
        self._plain = NoColor()
        self._filters.append(self._plain)
        self._set_look()
        backdrop.install()
        self._told: dict = {}

    def on_mount(self):
        self.underlay = Underlay(self)
        self.underlay.start()
        self.app_resume_signal.subscribe(self, lambda app: self.force_full_repaint())
        self.run_worker(self._remember_good_config, thread=True, group="known-good")
        self.push_screen(HomeScreen())
        self._fit_to_height(self.size.height)

    def _set_look(self):
        minimal = settings.is_minimal()
        self.set_class(minimal, "-minimal")
        self.theme = "ansi-dark" if minimal else "paws"
        self._plain.enabled = minimal

    def run_job(self, label, work, finish=None):
        """work(progress) runs in a thread and belongs to the app, not a screen, so leaving the screen doesn't stop
        it and every screen's bar keeps showing it. finish(result) runs after, result being what work returned or the
        error it raised"""
        if self.job.active:
            self.tell("busy", f"still {self.job.label}, wait for it to finish", "warning")
            return False
        self.job.start(label)

        def body():
            try:
                result = work(self.job.progress)
            except Exception as error:
                result = error
            self.call_from_thread(self._end_job, finish, result)

        self.run_worker(body, thread=True, group="job")
        return True

    def _end_job(self, finish, result):
        self.job.done()
        if finish is not None:
            finish(result)

    def call_from_thread(self, callback, *args, **kwargs):
        # a worker that finishes after its screen was rebuilt or closed must not take the whole app down
        def safe():
            try:
                return callback(*args, **kwargs)
            except NoMatches:
                return None

        return super().call_from_thread(safe)

    async def apply_look(self, settings_row=0):
        """riced <-> minimal without a restart: theme, background picture, icons, then every open screen is rebuilt"""
        from .screens.settings import SettingsScreen
        from .widgets import icons

        self._set_look()
        icons.reset()
        self.underlay.stop()
        self.underlay = Underlay(self)
        self.underlay.start()
        stack = [type(s) for s in self.screen_stack[1:] if not isinstance(s, ModalScreen)]
        for _ in range(len(self.screen_stack) - 1):
            await self.pop_screen()
        await self.push_screen(HomeScreen())
        if SettingsScreen in stack:
            await self.push_screen(SettingsScreen(settings_row))
        self.force_full_repaint()

    def _remember_good_config(self):
        from .. import repair

        try:
            repair.refresh_known_good()
        except Exception:
            pass

    def on_unmount(self):
        if getattr(self, "underlay", None) is not None:
            self.underlay.stop()

    def on_resize(self, event):
        hires.cell()
        self._fit_to_height(event.size.height)

    def force_full_repaint(self):
        try:
            screen = self.screen
            screen._compositor._dirty_regions.add(screen.size.region)
            screen._compositor_refresh()
        except Exception:
            pass

    LONG_JOB = 8.0

    def tell(self, title: str, body: str = "", severity: str = "information", took: float = 0.0):
        mode = "toasts" if settings.is_minimal() else str(settings.get_setting("notifications") or "auto")
        if mode == "off":
            return
        key = (title, body)
        now = time.monotonic()
        if now - self._told.get(key, -99.0) < 2.0:
            return
        self._told[key] = now
        try:
            self.notify(body or title, title=title if body else "", severity=severity, timeout=6)  # type: ignore[arg-type]
        except Exception:
            pass
        popup = mode == "always" or (mode == "auto" and (not self.app_focus or took >= self.LONG_JOB))
        if popup and mode != "toasts":
            urgency = "critical" if severity == "error" else "normal"
            self.run_worker(lambda: notify.send(title, body, urgency), thread=True, group="notify")

    def edit_config(self, line: int | None = None, done=None):
        from .. import editor
        from ..config import ensure_config
        from .widgets.modals import Confirm

        path = ensure_config()
        under = getattr(self, "underlay", None)
        if under is not None:
            under.pause()
        try:
            result = editor.edit(path, line, suspend=self.suspend)
        finally:
            if under is not None:
                under.resume()
            self.force_full_repaint()

        def finish():
            if done is not None:
                done()

        if not result.ran:
            self.tell("couldn't open the editor", result.error, "error")
            return finish()
        if result.problem:

            def answer(yes: bool | None):
                if yes and editor.put_back(path, result.backup):
                    self.tell("your old config is back", "the edit had a yaml error")
                finish()

            self.push_screen(
                Confirm(
                    f"config.yaml is broken yaml now:\n{result.problem}\n\nput the version from before your edit back?\n"
                    "(no: keep your edit and fix it yourself)",
                    "Config problem",
                    dangerous=True,
                ),
                answer,
            )
            return None
        self.tell(
            f"saved in {result.editor}" if result.changed else "nothing changed",
            "checked: it's valid yaml" if result.changed else "",
        )
        finish()

    def action_drop_zone(self):
        if not isinstance(self.screen, ModalScreen):
            self.push_screen(DropScreen())

    async def on_event(self, event: events.Event):
        if isinstance(event, events.Paste) and not event.is_forwarded:
            can_take = isinstance(self.screen, DropScreen) or not isinstance(self.screen, ModalScreen)
            take_ticket = getattr(self.screen, "take_pasted", None)
            if take_ticket is not None and not isinstance(self.focused, TextArea) and take_ticket(event.text):
                event.stop()
                return
            build = drop.build_source_from_text(event.text)
            typing = isinstance(self.focused, (Input, TextArea))
            if build is not None and can_take and not (typing and build.startswith(("http", "git@"))):
                event.stop()
                await self.confirm_build_install(build)
                return
            listed = drop.list_file_text(event.text)
            if listed is not None and can_take:
                parsed = textdrop.parse_text(listed)
                if parsed.items or parsed.kind == "depots":
                    event.stop()
                    await self.take_text(parsed)
                    return
            files = drop.dropped_files(event.text)
            if files is not None and can_take:
                event.stop()
                await self.take_drop(files)
                return
            if can_take and (textdrop.is_multiline(event.text) or drop.is_bare_id(event.text)):
                parsed = textdrop.parse_text(event.text)
                focused = self.focused
                if drop.wants_text(
                    parsed,
                    focus_is_input=isinstance(focused, Input),
                    focus_is_textarea=isinstance(focused, TextArea),
                    text=event.text,
                ):
                    event.stop()
                    await self.take_text(parsed)
                    return
        await super().on_event(event)

    async def take_drop(self, files):
        result = await asyncio.to_thread(drop.import_any, files)
        self.tell(result.title, "; ".join(x for x in result.lines if x)[:200], "information" if result.ok else "error")
        if isinstance(self.screen, DropScreen):
            self.screen.show_result(result)
        else:
            self.push_screen(DropScreen(result))

    async def take_text(self, parsed):
        result = await asyncio.to_thread(drop.import_text, parsed)
        self.tell(result.title, "; ".join(x for x in result.lines if x)[:200], "information" if result.ok else "error")
        if isinstance(self.screen, DropScreen):
            self.screen.show_result(result)
        else:
            self.push_screen(DropScreen(result))

    async def confirm_build_install(self, source):
        from .. import sls
        from .widgets.modals import Confirm

        product = "HeadCrab" if re.search(r"head|h3ad", source, re.I) else "SLSsteam"

        def answer(yes):
            if not yes:
                return
            build = sls.SlsSource(product, "private", url=source)
            self.run_worker(lambda: self._install_build(build), thread=True, exclusive=True, group="sls-run")

        self.push_screen(
            Confirm(f"{source}\nlooks like a {product} build. install it as a private build?"),
            answer,
        )

    def _install_build(self, source):
        from .. import sls

        try:
            sls.install_release(source)
        except Exception as error:
            self.call_from_thread(self.tell, "couldn't install build", str(error)[:200], "error")
            return
        self.call_from_thread(self.tell, "SLSsteam installed", "private build installed")

    def _fit_to_height(self, rows):
        self.set_class(rows < 30, "-short")


def main() -> int:
    PawApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
