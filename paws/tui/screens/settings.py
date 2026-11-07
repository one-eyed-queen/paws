from __future__ import annotations

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import ListItem, Static

from ... import __version__
from ... import appentry
from ... import launch
from ... import notify
from ... import riced
from ... import settings
from .. import colorblind
from ..widgets.footer import FooterHelp
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar
from ..widgets.menu import Menu, MenuItem, restore_index
from ..widgets.modals import Confirm, ModalInput, ModalPick

RICED_ROWS = {"nsfw", "random_banner", "notifications", "notify_sound"}
OK, OFF, CYAN = "#5ff0a0", "#9aa5c4", "#00d0ff"
CYCLES = {
    "notifications": ("auto", "always", "toasts", "off"),
    "icons": ("auto", "nerd", "plain", "none"),
}
MODE_NOTES = {
    "protanopia": "red looks weak or dark",
    "deuteranopia": "green looks weak, the most common kind",
    "tritanopia": "blue and yellow get mixed up",
    "monochrome": "no colours at all, greys only",
}


def switch(on: bool) -> str:
    return f"[b {OK}]━━● on [/]" if on else f"[{OFF}]●━━ off[/]"


def choice(value) -> str:
    return f"[b {CYAN}]{value}  ▾[/]"


class SectionRow(ListItem):
    """a heading between the rows. disabled, so the arrow keys step over it"""

    def __init__(self, title: str):
        super().__init__(disabled=True, classes="set-section")
        self.data = None
        self.title = title

    def render(self):
        return Text.from_markup(f"[b #d5deff]{self.title}[/]")


class SettingsScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [
        ("escape", "pop", "back"),
        ("backspace", "pop", "back"),
        ("left", "step(-1)", "previous choice"),
        ("right", "step(1)", "next choice"),
    ]

    def __init__(self, start="colorblind_on", **kwargs):
        super().__init__(**kwargs)
        self.start = start

    def compose(self) -> ComposeResult:
        yield AppHeader("Settings", id="hdr")
        yield Menu(id="set-menu", classes="panel")
        yield Static("", id="set-out", classes="panel")
        yield FooterHelp("↑↓ move · enter or space changes · ← → steps through choices · esc back")
        yield JobBar(id="job")

    def on_mount(self):
        self._rows_now = ()
        self.rebuild(self.start)

    def key_space(self):
        self.query_one("#set-menu", Menu).action_select_cursor()

    def _sections(self):
        """(heading, rows), where a row is (key, label, control, description, icon)"""
        get = settings.get_setting
        term = str(get("terminal"))
        mode = colorblind.mode()
        kind = mode if mode != "off" else colorblind.last_kind()
        out = [
            (
                "Colour blind",
                [
                    (
                        "colorblind_on",
                        "Colour blind mode",
                        switch(mode != "off"),
                        "changes every colour paws draws: text, backgrounds and pictures. works in riced and minimal.",
                        "settings",
                    ),
                    (
                        "colorblind_kind",
                        "Type",
                        choice(kind),
                        f"{MODE_NOTES[kind]}. enter opens the list, ← → steps through it.",
                        "settings",
                    ),
                ],
            ),
            (
                "Look",
                [
                    (
                        "type",
                        "Style",
                        choice(settings.ui_type()),
                        "riced: background picture, banner and ascii art. minimal: plain text on your terminal's own "
                        "background.",
                        "settings",
                    ),
                    ("icons", "Menu icons", choice(get("icons")), "auto uses a nerd font when one is installed. takes effect next start.", "settings"),
                    ("random_banner", "Random banner", switch(get("random_banner")), "new home art every time you get to the menu", "banner"),
                    ("nsfw", "NSFW art", switch(get("nsfw")), "show 18+ art in the gallery, never while this is off", "nsfw"),
                ],
            ),
            (
                "Startup and updates",
                [
                    ("auto_update", "Update on start", switch(get("auto_update")), f"look for a newer paws before the menu opens, at most once every {get('update_interval_min')} min", "settings"),
                    ("auto_add_games", "Live config fixer", switch(get("auto_add_games")), "quietly adds games that are in the config but weren't added properly, and names the rows. runs at start and whenever the config changes.", "settings"),
                    ("live_update", "Check for updates while running", switch(get("live_update")), "every few minutes while paws is open. when a new version is out a small popup offers to update and restart", "settings"),
                    ("restart", "Restart paws", f"[{CYAN}]↻[/]", "close paws and open it again right here", "settings"),
                    ("check_update", "Check for an update now", f"[{CYAN}]v{__version__}[/]", "ask github now, even with auto-update off", "settings"),
                ],
            ),
            (
                "Notifications",
                [
                    ("notifications", "Notifications", choice(get("notifications")), "auto: a desktop popup when paws is in the background or a job took long. always: every time. toasts: only inside paws. off: nothing.", "settings"),
                    ("notify_sound", "Sound", switch(get("notify_sound")), "play a sound with desktop popups", "settings"),
                ],
            ),
            (
                "Terminal and launcher",
                [
                    ("terminal", "Terminal", choice(term), "which terminal `paws --window` opens: auto, " + ", ".join(launch.installed_terminals()), "terminal"),
                    ("shortcut", "Desktop shortcut", switch(appentry.has_shortcut()), f"a paws icon on your desktop ({appentry.shortcut_file()})", "terminal"),
                    ("entry", "App menu entry", switch(appentry.has_entry()), "paws in your app menu and dock, with its icon", "terminal"),
                    ("launch_cmd", "Launcher command", f"[{CYAN}]{get('launch_cmd')}[/]", "the command that opens paws in a terminal (default: paws)", "terminal"),
                ],
            ),
        ]
        minimal = settings.is_minimal()
        features = [
            (f"feat:{f}", settings.FEATURE_LABELS[f], switch(not settings.is_disabled(f)), settings.FEATURE_DESCS[f], "settings")
            for f in settings.FEATURES
            if not (minimal and f in settings.RICED_ONLY) and not settings.hidden_for_now(f)
        ]
        out.append(("Home menu", features))
        return [(title, [r for r in rows if not (minimal and r[0] in RICED_ROWS)]) for title, rows in out]

    def rebuild(self, keep=None):
        """only what changed gets redrawn. tearing the whole list down on every toggle is what made this page lag"""
        menu = self.query_one("#set-menu", Menu)
        sections = self._sections()
        shape = tuple(row[0] for _title, rows in sections for row in rows)
        if shape != self._rows_now:
            self._rows_now = shape
            menu.remove_children()
            for title, rows in sections:
                menu.append(SectionRow(title))
                for key, label, control, desc, icon_name in rows:
                    menu.append(MenuItem(key, label, desc, icon_name, hint=control))
            index = next((i for i, row in enumerate(menu.children) if row.data == keep), 1)
            menu.focus()
            menu.call_after_refresh(lambda: restore_index(menu, index))
            return
        controls = {row[0]: row for _title, rows in sections for row in rows}
        for item in menu.query(MenuItem):
            item.desc = controls[item.data][3]
            item.set_hint(controls[item.data][2])
        if menu.highlighted_child is not None:
            self.query_one("#set-out", Static).update(menu.highlighted_child.desc)

    def _current(self):
        item = self.query_one("#set-menu", Menu).highlighted_child
        return item.data if item is not None else None

    def _flip(self, key):
        settings.set_setting(key, not settings.get_setting(key))

    def _set_colorblind(self, value):
        settings.set_setting("colorblind", value)
        if value != "off":
            settings.set_setting("colorblind_kind", value)
        self.app.apply_colours()
        self.rebuild()

    def _pick_kind(self):
        current = colorblind.mode() if colorblind.mode() != "off" else colorblind.last_kind()
        options = [
            (f"{'● ' if kind == current else '  '}{kind}", kind, None, MODE_NOTES[kind])
            for kind in colorblind.KINDS
        ]
        self.app.push_screen(
            ModalPick("Colour blind type", "the one you pick turns the mode on", options),
            lambda kind: self._set_colorblind(kind) if kind else None,
        )

    def action_step(self, by):
        key = self._current()
        if key == "colorblind_kind":
            kinds = colorblind.KINDS
            current = colorblind.mode() if colorblind.mode() != "off" else colorblind.last_kind()
            self._set_colorblind(kinds[(kinds.index(current) + by) % len(kinds)])
        elif key in CYCLES or key == "terminal":
            self._cycle(key, by)
            self.rebuild()

    def _cycle(self, key, by=1):
        order = ("auto", *launch.installed_terminals()) if key == "terminal" else CYCLES[key]
        current = str(settings.get_setting(key))
        settings.set_setting(key, order[(order.index(current) + by) % len(order)] if current in order else "auto")

    @on(Menu.Selected)
    def _sel(self, ev):
        if ev.item is None or ev.item.data is None:
            return
        data = ev.item.data
        note = ""
        if data == "colorblind_on":
            on_now = colorblind.mode() != "off"
            self._set_colorblind("off" if on_now else colorblind.last_kind())
            return
        if data == "colorblind_kind":
            self._pick_kind()
            return
        if data == "nsfw":
            self._flip("nsfw")
            message = "HENTAI!!!" if settings.get_setting("nsfw") else "SIGMA!!!"
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
            self.app.call_later(self.app.apply_look, "type")
            return
        elif data == "restart":
            self.app.restart()
            return
        elif data in ("random_banner", "auto_update", "auto_add_games", "notify_sound", "live_update"):
            self._flip(data)
        elif data == "check_update":
            note = "checking github..."
            self._check_update()
        elif data in CYCLES or data == "terminal":
            self._cycle(data)
            if data == "icons":
                note = "icons change next time paws starts"
        elif data == "shortcut":
            note = (appentry.remove_shortcut() if appentry.has_shortcut() else appentry.add_shortcut()).note
        elif data == "entry":
            note = (appentry.uninstall() if appentry.has_entry() else appentry.install()).note
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
        self.rebuild()
        if note:
            self.query_one("#set-out", Static).update(note)

    def _set_launch_cmd(self, value):
        if value:
            settings.set_setting("launch_cmd", value.strip() or "paws")
            self.rebuild()

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
            self.query_one("#set-out", Static).update(f"[#ff7a8a]{done.message}[/]")
            self.app.tell("paws update failed", done.message, "error")

    @on(Menu.Highlighted)
    def _hi(self, ev):
        if ev.item:
            self.query_one("#set-out", Static).update(ev.item.desc)

    def action_pop(self):
        self.app.pop_screen()
