from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import time

from textual import events
from textual.app import App
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.filter import NoColor
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Input, TextArea

from .. import drop, notify, settings, textdrop
from ..sls import share
from . import colorblind
from .jobs import Job


def _escape_markup(text: str) -> str:
    """paths get shown in markup-rendered labels, so a "[" in a folder name would otherwise
    swallow the rest of the sentence"""
    from rich.markup import escape

    return escape(text)


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


class PawsApp(App):
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
        # a daemon thread, not a worker: asyncio waits for worker threads on exit, and these lookups can take minutes,
        # which left quit hanging until ctrl+c. everything here is saved as it goes, so dying mid-way loses nothing
        self._fixer_busy = False
        self._start_fixer()
        self.set_interval(LIVE_UPDATE_EVERY, self._live_update_check)
        self.run_doctor()
        self.set_interval(3.0, self._watch_config)
        self.push_screen(HomeScreen())
        self._fit_to_height(self.size.height)
        self.call_after_refresh(self._drop_splash)

    def _drop_splash(self):
        if os.name != "nt":
            from ..update.glass import remove_picture

            self.underlay._send(remove_picture())

    def _set_look(self):
        minimal = settings.is_minimal()
        self.set_class(minimal, "-minimal")
        self.theme = "ansi-dark" if minimal else "paws"
        self._plain.enabled = minimal
        old = getattr(self, "_colorblind", None)
        if old in self._filters:
            self._filters.remove(old)
        self._colorblind = colorblind.filter_for(minimal)
        if self._colorblind is not None:
            self._filters.append(self._colorblind)

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

    def apply_colours(self):
        """a colour blind mode, in place: same screens, same cursor, only the colours and pictures change"""
        from .widgets import backdrop as backdrops

        self._set_look()
        self.underlay.stop()
        self.underlay = Underlay(self)
        self.underlay.start()
        backdrops.forget_colours()
        for screen in self.screen_stack:
            screen._base_rgb = None
            for widget in [screen, *screen.walk_children()]:
                recolour = getattr(widget, "recolour", None)
                if recolour is not None:
                    recolour()
                kept = getattr(widget, "backdrop", None)
                if kept is not None:
                    kept._size = None
                widget._styles_cache.clear()
                widget.refresh()
        self.force_full_repaint()

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
        with self.batch_update():  # all in one paint, the menu must not flash on the way back to settings
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

    RESTART_CODE = 75

    def restart(self):
        """quits, and main() starts paws again in the same terminal"""
        self.exit(return_code=self.RESTART_CODE)

    _update_offered = None

    def _live_update_check(self):
        if not settings.get_setting("live_update") or self._update_offered:
            return
        threading.Thread(target=self._look_for_update, name="paws-live-update", daemon=True).start()

    def _look_for_update(self):
        from .. import update

        try:
            status = update.check()
        except Exception:
            return
        if status.can_apply and self.is_running:
            self.call_from_thread(self._offer_update, status)

    def _offer_update(self, status):
        from .widgets.modals import UpdatePopup

        if self._update_offered:
            return
        self._update_offered = status
        self.push_screen(UpdatePopup(status), lambda _done: setattr(self, "_update_offered", None))

    doctor_report = None
    doctor_at = 0.0
    doctor_busy = False

    def run_doctor(self):
        """once when paws opens, then only when asked: the status page just shows the last answer"""
        if self.doctor_busy:
            return
        self.doctor_busy = True
        threading.Thread(target=self._doctor_worker, name="paws-doctor", daemon=True).start()

    def _doctor_worker(self):
        from .. import doctor

        report = doctor.Doctor()
        self.doctor_report = report  # rows show up on the page as they come in
        try:
            for _ in report.stream():
                pass
            self.doctor_at = time.time()
        finally:
            self.doctor_busy = False

    def _config_stamp(self):
        from ..config.where import find_config

        try:
            return find_config().stat().st_mtime_ns
        except (OSError, AttributeError):
            return None

    def _start_fixer(self):
        self._fixer_busy = True
        threading.Thread(target=self._add_missing_games, name="paws-bg-add", daemon=True).start()

    def _watch_config(self):
        """the live fixer: an edit made by hand, or by anything else, gets the same treatment as a start. it waits for
        the file to stop changing and leaves a config that doesn't parse alone, that's somebody halfway through a save"""
        stamp = self._config_stamp()
        if self._fixer_busy or stamp is None or stamp == self._fixed_stamp:
            self._pending_stamp = None
            return
        if stamp != getattr(self, "_pending_stamp", None):
            self._pending_stamp = stamp
            return
        self._pending_stamp = None
        from .. import config

        try:
            config.parsed()
        except Exception:
            self._fixed_stamp = stamp
            return
        self._start_fixer()

    _fixed_stamp = None

    def _add_missing_games(self):
        try:
            self._add_missing_games_once()
        finally:
            self._fixed_stamp = self._config_stamp()  # our own writes don't count as a new edit
            self._fixer_busy = False

    def _add_missing_games_once(self):
        from ..games.background import run

        # quiet on purpose: small things get fixed behind the menu, a broken config is what the home screen warns about
        try:
            added = run()
        except Exception:  # the next start or config change tries again
            return
        if added and self.is_running:
            self.call_from_thread(self._tell_fixed, added)

    def _tell_fixed(self, added):
        if isinstance(self.screen, DropScreen):  # a drop's own follow-up: the card already covers it
            return
        self.tell(f"fixed {len(added)} game(s)", ", ".join(added))

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
            if can_take and not isinstance(self.focused, TextArea) and share.find_code(event.text):
                event.stop()
                self.run_worker(lambda: self.take_ticket_code(event.text), thread=True, group="take-ticket")
                return
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
            if listed is not None and can_take and share.find_code(listed):  # a code saved in a .txt, dropped
                event.stop()
                self.run_worker(lambda: self.take_ticket_code(listed), thread=True, group="take-ticket")
                return
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

    def take_ticket_code(self, text):
        """on a worker: adding the game asks the store"""
        missing = settings.missing_reason()
        try:
            if missing:
                raise ValueError(missing)
            saved = share.take_code(text)
        except (ValueError, OSError) as error:
            self.call_from_thread(self.tell, "couldn't take those tickets", str(error), "error")
            return
        names = ", ".join(t.filename for t in saved)
        self.call_from_thread(self.tell, f"saved {len(saved)} shared ticket(s)", names)
        redraw = getattr(self.screen, "_draw_tickets", None)
        if redraw is not None:
            self.call_from_thread(redraw)

    async def _import(self, work, what):
        """a drop can't reach the hidden menus' work either: same error instead of writing to a config nothing reads"""
        missing = settings.missing_reason()
        if missing:
            return drop.DropResult(False, "nothing added", [missing])
        return await asyncio.to_thread(work, what)

    async def take_drop(self, files):
        # the drop card says all of this itself; toasts on top of it read as a second, broken popup
        result = await self._import(drop.import_any, files)
        if isinstance(self.screen, DropScreen):
            self.screen.show_result(result)
        else:
            self.push_screen(DropScreen(result))

    async def take_text(self, parsed):
        result = await self._import(drop.import_text, parsed)
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

        # the path goes into a markup-rendered label, so a "[" in it would eat the rest of the
        # sentence. escape it rather than let the dialog fall apart
        self.push_screen(
            Confirm(f"{_escape_markup(source)}\nlooks like a {product} build. install it as a private build?"),
            answer,
        )

    def _install_build(self, source):
        from pathlib import Path

        from .. import sls

        try:
            result, wired = sls.install_release(source)
        except Exception as error:
            self.call_from_thread(self.tell, "couldn't install build", str(error)[:200], "error")
            return
        # "it didn't raise" is not the same as "it installed". an archive with no compiled
        # library in it used to come back clean and report a cheerful success while writing
        # nothing, which is why dropping a release looked like it did nothing at all
        so = getattr(result, "sls_so", None) if result else None
        if not so or not Path(so).exists():
            self.call_from_thread(
                self.tell,
                "SLSsteam not installed",
                "no built library in that file - looks like source code, not a release",
                "error",
            )
            return
        wired_names = ", ".join(Path(p).name for p in wired)
        others = sls.other_installs(keep=result.lib_dir)
        body = f"{Path(so).name} in place - steam will inject {wired_names or 'nothing'}"
        if others:
            body += "\n\nalso installed: " + "\n".join(others)
        self.call_from_thread(self.tell, "SLSsteam installed", body)

    def _fit_to_height(self, rows):
        self.set_class(rows < 34, "-short")


LIVE_UPDATE_EVERY = 300.0


def _start_again():
    """a fresh process, same terminal: new code from an update loads properly this way"""
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, "-m", "paws", *sys.argv[1:]])


def main() -> int:
    app = PawsApp()
    app.run()
    if app.return_code == PawsApp.RESTART_CODE:
        _start_again()
    # the terminal is back to normal by now. leaving through python would still sit waiting on any lookup that's in
    # flight, and every write those make is atomic, so leave now
    if threading.active_count() > 1 and not os.environ.get("PAWS_HOLD"):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(app.return_code or 0)
    return app.return_code or 0


if __name__ == "__main__":
    raise SystemExit(main())
