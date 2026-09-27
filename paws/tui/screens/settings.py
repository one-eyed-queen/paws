from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from ... import __version__
from ... import appentry
from ... import launch
from ... import notify
from ... import riced
from ... import settings
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar
from ..widgets.menu import Menu, MenuItem, restore_index
from ..widgets.modals import Confirm, ModalInput

RICED_ROWS = {"nsfw", "random_banner", "notifications", "notify_sound"}
OK, OFF, DIM, CYAN = "#3ddc97", "#ff5c7a", "#6b7aa8", "#00d0ff"


class SettingsScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def __init__(self, start=0, **kwargs):
        super().__init__(**kwargs)
        self.start = start

    def compose(self) -> ComposeResult:
        yield AppHeader("Settings", id="hdr")
        yield Static(
            "[#9db0e0]18+ art only shows when NSFW mode is on · a feature you turn off disappears from the home menu[/]",
            id="set-hint",
            classes="panel",
        )
        yield Menu(id="set-menu", classes="panel")
        yield Static("", id="set-out", classes="panel")
        yield JobBar(id="job")

    def on_mount(self):
        self.rebuild(self.start)

    @staticmethod
    def _box(on):
        return f"[{OK}]☑[/]" if on else f"[{DIM}]☐[/]"

    @staticmethod
    def _state(on, words=("on", "off")):
        return f"[{OK}]{words[0]}[/]" if on else f"[{OFF}]{words[1]}[/]"

    def rebuild(self, keep: int = 0):
        menu = self.query_one("#set-menu", Menu)
        menu.remove_children()
        get = settings.get_setting
        term = str(get("terminal"))
        rows = [
            (
                "nsfw",
                f"NSFW art mode  {self._state(get('nsfw'), ('ON', 'OFF'))}",
                "show 18+ art in the gallery, never while this is off",
                "nsfw",
            ),
            (
                "type",
                f"Type  [{CYAN}]{settings.ui_type()}[/]",
                "riced: background picture, banner and ascii art. minimal: plain text, lines and boxes on your "
                "terminal's own background. Enter switches, right away.",
                "settings",
            ),
            (
                "random_banner",
                f"Random banner  {self._state(get('random_banner'))}",
                "new home art every time you get to the menu",
                "banner",
            ),
            (
                "auto_update",
                f"Update on start  {self._state(get('auto_update'))}",
                "check github for a newer paws before the menu opens and pull it in (at most once every "
                f"{get('update_interval_min')} min)",
                "settings",
            ),
            (
                "check_update",
                f"Check for a paws update now  [{CYAN}]v{__version__}[/]",
                "ask github now, even with auto-update off. if there's something newer it offers to install it.",
                "settings",
            ),
            (
                "notifications",
                f"Notifications  [{CYAN}]{get('notifications')}[/]",
                "auto: a desktop popup when paws is in the background or a job took long. always: every time. toasts: only inside paws. off: nothing. Enter cycles.",
                "settings",
            ),
            (
                "notify_sound",
                f"Notification sound  {self._state(get('notify_sound'))}",
                "play a sound with desktop popups. off keeps them silent.",
                "settings",
            ),
            (
                "icons",
                f"Menu icons  [{CYAN}]{get('icons')}[/]",
                "auto uses a nerd font's icons when one is installed, plain symbols otherwise. Enter cycles auto / nerd / plain / none. Takes effect next start.",
                "settings",
            ),
            (
                "terminal",
                f"Terminal / console  [{CYAN}]{term}[/]",
                "Which terminal `paws --window` opens. Enter cycles: auto, "
                + ", ".join(launch.installed_terminals())
                + ".",
                "terminal",
            ),
            (
                "shortcut",
                f"{self._box(appentry.has_shortcut())} Desktop shortcut",
                f"A paws icon on your desktop ({appentry.shortcut_file()}). Tick it to add, untick to remove.",
                "terminal",
            ),
            (
                "entry",
                f"{self._box(appentry.has_entry())} App menu entry + icon",
                "paws in your app menu and dock, with its icon. tick to add, untick to remove.",
                "terminal",
            ),
            (
                "launch_cmd",
                f"Launcher command  [{CYAN}]{get('launch_cmd')}[/]",
                "the command that opens paws in a terminal (default: paws)",
                "terminal",
            ),
        ]
        minimal = settings.is_minimal()
        for key, label, desc, icon_name in rows:
            if minimal and key in RICED_ROWS:
                continue
            menu.append(MenuItem(key, label, desc, icon_name))
        for feature in settings.FEATURES:
            if (minimal and feature in settings.RICED_ONLY) or (
                feature in settings.NEEDS_SLS and not settings.sls_present()
            ):
                continue
            on = not settings.is_disabled(feature)
            label = f"{settings.FEATURE_LABELS[feature]}  {self._state(on)}"
            menu.append(
                MenuItem(
                    f"feat:{feature}",
                    label,
                    settings.FEATURE_DESCS[feature],
                    "settings",
                )
            )
        menu.focus()
        menu.call_after_refresh(lambda: restore_index(menu, keep))

    @on(Menu.Selected)
    def _sel(self, ev):
        if ev.item is None:
            return
        data = ev.item.data
        keep = self.query_one("#set-menu", Menu).index or 0
        note = ""
        if data == "nsfw":
            turned_on = not settings.get_setting("nsfw")
            settings.set_setting("nsfw", turned_on)
            message = "HENTAI!!!" if turned_on else "SIGMA!!!"
            self.app.tell(message)
            self.run_worker(lambda: notify.send(message), thread=True, group="notify")
        elif data == "type":
            going_riced = settings.ui_type() == "minimal"
            if going_riced and not riced.installed():
                self.query_one("#set-out", Static).update(
                    "riced isn't installed (no pictures, art or games on this machine). "
                    "run ./scripts/install.sh --riced in the paws folder to get it."
                )
                return
            settings.set_setting("type", "riced" if going_riced else "minimal")
            self.app.call_later(self.app.apply_look, keep)
            return
        elif data == "random_banner":
            settings.set_setting("random_banner", not settings.get_setting("random_banner"))
        elif data == "auto_update":
            settings.set_setting("auto_update", not settings.get_setting("auto_update"))
        elif data == "check_update":
            note = "checking github..."
            self._check_update()
        elif data == "notifications":
            order = ["auto", "always", "toasts", "off"]
            current = str(settings.get_setting("notifications"))
            settings.set_setting("notifications", order[(order.index(current) + 1) % 4] if current in order else "auto")
        elif data == "notify_sound":
            settings.set_setting("notify_sound", not settings.get_setting("notify_sound"))
        elif data == "icons":
            order = ["auto", "nerd", "plain", "none"]
            current = str(settings.get_setting("icons"))
            settings.set_setting("icons", order[(order.index(current) + 1) % 4] if current in order else "auto")
            note = "icons change next time paws starts"
        elif data == "terminal":
            choices = ["auto", *launch.installed_terminals()]
            current = str(settings.get_setting("terminal"))
            nxt = choices[(choices.index(current) + 1) % len(choices)] if current in choices else "auto"
            settings.set_setting("terminal", nxt)
        elif data == "shortcut":
            result = appentry.remove_shortcut() if appentry.has_shortcut() else appentry.add_shortcut()
            note = result.note
        elif data == "entry":
            result = appentry.uninstall() if appentry.has_entry() else appentry.install()
            note = result.note
        elif data == "launch_cmd":
            self.app.push_screen(
                ModalInput(
                    "the command that opens paws in a terminal (default: paws)",
                    "Launcher command",
                    default=str(settings.get_setting("launch_cmd")),
                ),
                self._set_launch_cmd,
            )
        elif data.startswith("feat:"):
            settings.toggle_disabled(data[5:])
        self.rebuild(keep)
        if note:
            self.query_one("#set-out", Static).update(note)

    def _set_launch_cmd(self, value):
        if value:
            settings.set_setting("launch_cmd", value.strip() or "paws")
            self.rebuild(self.query_one("#set-menu", Menu).index or 0)

    @work(thread=True, exclusive=True, group="paws-update")
    def _check_update(self):
        from ... import update

        status = update.check()
        self.app.call_from_thread(self._show_update_status, status)

    def _show_update_status(self, status):
        from ...update import git

        lines = [f"[b]{status.state}[/b]: {status.message}"]
        if status.local and status.remote and status.local != status.remote:
            lines.append(f"[#9db0e0]{git.short(status.local)} -> {git.short(status.remote)}[/]")
        for subject in status.subjects[:8]:
            lines.append(f"[#9db0e0]+ {subject}[/]")
        self.query_one("#set-out", Static).update("\n".join(lines))
        if status.can_apply:
            self.app.push_screen(
                Confirm(f"Pull and install {status.message}?", "Update paws"),
                lambda yes: self._apply_update(status) if yes else None,
            )

    def _apply_update(self, status):
        from ... import update

        self.app.run_job("updating", lambda progress: update.apply(status), self._show_applied)

    def _show_applied(self, done):
        if isinstance(done, Exception):
            self.app.tell("paws update failed", str(done), "error")
            return
        if not self.is_attached:
            self.app.tell("paws updated" if done.state == "updated" else "paws update failed", done.message)
            return
        if done.state == "updated":
            self.query_one("#set-out", Static).update(
                f"[b #87d787]{done.message}[/]   [#9db0e0]quit and reopen paws to use it[/]"
            )
            self.app.tell("paws updated", "quit and reopen it to use the new build")
        else:
            self.query_one("#set-out", Static).update(f"[red]{done.message}[/]")
            self.app.tell("paws update failed", done.message, "error")

    @on(Menu.Highlighted)
    def _hi(self, ev):
        if ev.item:
            self.query_one("#set-out", Static).update(ev.item.desc)

    def action_pop(self):
        self.app.pop_screen()
