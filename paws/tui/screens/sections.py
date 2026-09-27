from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Static

from ... import editor
from ...config import editing as ed
from ...config import fill_missing, find_config, missing_keys
from ...config.schema import SECTIONS
from ...util import backup
from ..widgets.footer import FooterHelp
from ..widgets.header import AppHeader
from ..widgets.menu import Menu, MenuItem
from ..widgets.modals import ModalInput

NO_FILE = "no config.yaml yet: it gets made when you change something (or press Fill missing)"


def colour(value: str, is_default: bool) -> str:
    tint = "#87d787" if value == "yes" else "#7b88ad" if value in ("no", "empty", "off", "0 rows") else "#dbe4ff"
    return f"[{tint}]{value}[/]" + ("" if is_default else " [#ffd75f]●[/]")


class SectionsScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [
        Binding("escape", "back", "back"),
        Binding("slash", "filter", "filter", show=False),
        Binding("e", "edit_file", "edit in nvim/nano", show=False),
        Binding("space", "flip", "switch", show=False),
        Binding("r", "reset", "reset", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_key: str | None = None

    def compose(self) -> ComposeResult:
        yield AppHeader("Config editor", id="hdr")
        with Horizontal(id="cfg-body"):
            with Vertical(id="cfg-left", classes="panel"):
                yield Input(placeholder="filter: name or group", id="cfg-filter")
                yield Menu(id="sec-menu")
            with VerticalScroll(id="cfg-right", classes="panel"):
                yield Static("", id="cfg-info", markup=True)
                with Vertical(id="cfg-bool"):
                    with Horizontal(classes="cfg-buttons"):
                        yield Button("Switch", id="cfg-flip", variant="primary")
                        yield Button("Back to default", id="cfg-reset-b")
                with Vertical(id="cfg-value"):
                    yield Input(id="cfg-input")
                    with Horizontal(classes="cfg-buttons"):
                        yield Button("Save", id="cfg-save", variant="primary")
                        yield Button("Back to default", id="cfg-reset-v")
                with Vertical(id="cfg-rows"):
                    yield DataTable(id="cfg-table", cursor_type="row", zebra_stripes=True)
                    with Horizontal(classes="cfg-buttons"):
                        yield Button("Add row", id="cfg-add", variant="primary")
                        yield Button("Remove row", id="cfg-remove")
                yield Button("Edit this in the editor", id="cfg-jump")
        with Horizontal(id="cfg-tools"):
            yield Button("Edit file", id="cfg-edit", variant="warning")
            yield Button("Check", id="cfg-check")
            yield Button("Fill missing", id="cfg-fill")
            yield Button("Undo", id="cfg-undo")
        yield Static("", id="sec-out", classes="panel")
        yield FooterHelp("↑↓ pick · enter or space changes · / filter · e edits the file in nvim/nano · esc back")

    async def on_mount(self):
        self.query_one("#cfg-edit", Button).label = f"Edit file in {editor.editor_name()}"
        self.query_one("#cfg-jump", Button).label = f"Edit this in {editor.editor_name()}"
        await self._fill_list("")
        self.query_one("#sec-menu", Menu).focus()
        self.say("")

    async def _fill_list(self, needle, keep=None):
        menu = self.query_one("#sec-menu", Menu)
        needle = needle.strip().lower()
        keys = [
            k
            for k in ed.ordered_keys()
            if not needle
            or needle in k.lower()
            or needle in ed.group_of(k).lower()
            or needle in SECTIONS["sections"][k]["desc"].lower()
        ]
        groups = [name for _tag, name in ed.GROUPS]
        await menu.clear()
        snap = ed.Snapshot()
        items = [
            MenuItem(
                k,
                k,
                ed.group_of(k),
                "box",
                hue=groups.index(ed.group_of(k)) / max(len(groups) - 1, 1),
                hint=self._value_text(k, snap),
            )
            for k in keys
        ]
        await menu.extend(items)
        if keys:
            want = keys.index(keep) if keep in keys else 0
            menu.index = want
            self.show(keys[want])
        else:
            self.current_key = None
            self.query_one("#cfg-info", Static).update("[#9db0e0]nothing matches that[/]")
            self._show_mode(None)

    @staticmethod
    def _value_text(key, snap=None):
        snap = snap or ed.Snapshot()
        return colour(ed.summary(key, snap), ed.is_default(key, snap))

    def _refresh_row(self, key):
        for item in self.query_one("#sec-menu", Menu).query(MenuItem):
            if item.data == key:
                item.set_hint(self._value_text(key))

    @on(Input.Changed, "#cfg-filter")
    def _filtered(self, ev):
        timer = getattr(self, "_filter_timer", None)
        if timer is not None:
            timer.stop()
        self._filter_timer = self.set_timer(0.12, self._refill)

    def action_filter(self):
        self.query_one("#cfg-filter", Input).focus()

    @on(Input.Submitted, "#cfg-filter")
    def _filter_done(self):
        self.query_one("#sec-menu", Menu).focus()

    def action_back(self):
        box = self.query_one("#cfg-filter", Input)
        if box.has_focus or box.value:
            box.value = ""
            self.query_one("#sec-menu", Menu).focus()
            return
        self.app.pop_screen()

    @on(Menu.Highlighted, "#sec-menu")
    def _highlighted(self, ev):
        if ev.item is not None:
            self.show(ev.item.data)

    def show(self, key: str):
        self.current_key = key
        metadata = SECTIONS["sections"][key]
        mode = ed.mode(key)
        default = ed.default_of(key)
        lines = [
            f"[b #ffffff]{key}[/]   [#9db0e0]{ed.group_of(key)} · {metadata['type']}[/]",
            "",
            f"[#dbe4ff]{metadata['desc']}[/]",
            "",
        ]
        if mode in (ed.BOOL, ed.VALUE):
            lines.append(
                f"[#9db0e0]now[/] [b]{ed.current(key) or chr(34) * 2}[/]   [#9db0e0]default[/] {default if default != '' else chr(34) * 2}"
            )
        else:
            lines.append(f"[#9db0e0]{len(ed.block_rows(key))} row(s) in the file[/]")
        self.query_one("#cfg-info", Static).update("\n".join(lines))
        self._show_mode(mode)
        if mode == ed.BOOL:
            self.query_one("#cfg-flip", Button).label = "Turn off" if ed.current(key) == "yes" else "Turn on"
        elif mode == ed.VALUE:
            box = self.query_one("#cfg-input", Input)
            box.value = ed.current(key)
            box.placeholder = {"int": "a whole number", "hex": "hex, like 0x1"}.get(metadata["type"], "text")
        elif mode in (ed.ROWS, ed.NESTED):
            table = self.query_one("#cfg-table", DataTable)
            table.clear(columns=True)
            table.add_columns("row")
            for row in ed.block_rows(key):
                table.add_row(row)
            if not table.row_count:
                table.add_row("[#7b88ad](empty)[/]")
            for b in ("#cfg-add", "#cfg-remove"):
                self.query_one(b, Button).display = mode == ed.ROWS

    def _show_mode(self, mode):
        self.query_one("#cfg-bool").display = mode == ed.BOOL
        self.query_one("#cfg-value").display = mode == ed.VALUE
        self.query_one("#cfg-rows").display = mode in (ed.ROWS, ed.NESTED)
        self.query_one("#cfg-jump").display = mode is not None

    def say(self, text: str):
        if not text:
            path = find_config()
            text = f"[#9db0e0]editing[/] {path}" if path else f"[#ffd75f]{NO_FILE}[/]"
        self.query_one("#sec-out", Static).update(text)

    def _changed(self, key, message):
        self._refresh_row(key)
        self.show(key)
        self.say(message)

    @on(Menu.Selected, "#sec-menu")
    def _selected(self, ev):
        if ev.item is None:
            return
        mode = ed.mode(ev.item.data)
        if mode == ed.BOOL:
            self.action_flip()
        elif mode == ed.VALUE:
            self.query_one("#cfg-input", Input).focus()
        elif mode == ed.ROWS:
            self.query_one("#cfg-table", DataTable).focus()
        else:
            self.action_jump()

    def action_flip(self):
        key = self.current_key
        if key is None or ed.mode(key) != ed.BOOL:
            return
        new = ed.toggle(key)
        self._changed(key, f"[#87d787]{key}[/] is now [b]{new}[/]   [#9db0e0](Undo puts it back)[/]")

    def action_reset(self):
        key = self.current_key
        if key is None or ed.mode(key) not in (ed.BOOL, ed.VALUE):
            return
        d = ed.reset(key)
        self._changed(key, f"[#87d787]{key}[/] is back to its default: [b]{d or chr(34) * 2}[/]")

    @on(Button.Pressed, "#cfg-flip")
    def _flip_b(self):
        self.action_flip()

    @on(Button.Pressed, "#cfg-reset-b, #cfg-reset-v")
    def _reset_b(self):
        self.action_reset()

    @on(Button.Pressed, "#cfg-save")
    @on(Input.Submitted, "#cfg-input")
    def _save(self):
        key = self.current_key
        if key is None or ed.mode(key) != ed.VALUE:
            return
        text = self.query_one("#cfg-input", Input).value
        try:
            ed.set_value(key, text)
        except ValueError as e:
            self.say(f"[red]{key} needs {e}[/red]")
            return
        self._changed(key, f"[#87d787]{key}[/] saved: [b]{text.strip() or chr(34) * 2}[/]")

    @on(Button.Pressed, "#cfg-add")
    def _add(self):
        key = self.current_key
        if key is None or ed.mode(key) != ed.ROWS:
            return
        help_text = ed.ROW_HELP[SECTIONS["sections"][key]["type"]]
        self.app.push_screen(
            ModalInput(f"add a row to {key}\n{help_text}", "Add row"), lambda v, k=key: self._add_done(k, v)
        )

    def _add_done(self, key, text):
        if not text or not text.strip():
            return
        try:
            line = ed.add_row(key, text)
        except ValueError as e:
            self.say(f"[red]{e}[/red]")
            return
        self._changed(key, f"added [b]{line.strip()}[/b] to {key}")

    @on(Button.Pressed, "#cfg-remove")
    def _remove(self):
        key = self.current_key
        if key is None or ed.mode(key) != ed.ROWS:
            return
        table = self.query_one("#cfg-table", DataTable)
        rows = ed.block_rows(key)
        if not rows or table.cursor_row is None or table.cursor_row >= len(rows):
            self.say("pick a row in the list first")
            return
        row = rows[table.cursor_row]
        ed.remove_row(key, row)
        self._changed(key, f"removed [b]{row}[/b] from {key}   [#9db0e0](Undo puts it back)[/]")

    def action_edit_file(self):
        self._edit(None)

    def action_jump(self):
        path = find_config()
        self._edit(editor.section_line(path, self.current_key) if path and self.current_key else None)

    @on(Button.Pressed, "#cfg-edit")
    def _edit_b(self):
        self._edit(None)

    @on(Button.Pressed, "#cfg-jump")
    def _jump_b(self):
        self.action_jump()

    def _edit(self, line):
        self.app.edit_config(line, done=self._back_from_editor)

    def _back_from_editor(self):
        self.call_later(self._refill)
        self.say("")

    async def _refill(self):
        await self._fill_list(self.query_one("#cfg-filter", Input).value, keep=self.current_key)

    @on(Button.Pressed, "#cfg-check")
    def _check(self):
        problem = ed.file_problem()
        missing = missing_keys()
        removed = [k for k in SECTIONS.get("removed", []) if any(l.startswith(f"{k}:") for l in _lines())]
        out = ["[#ff5f5f]yaml problem: " + problem + "[/]"] if problem else ["[#87d787]the file is valid yaml[/]"]
        out.append(
            f"[#ffd75f]missing keys: {', '.join(missing)}[/]  (Fill missing adds them)"
            if missing
            else "[#87d787]every key SLSsteam reads is there[/]"
        )
        if removed:
            out.append(f"[#ffd75f]keys SLSsteam no longer reads: {', '.join(removed)}[/]")
        self.say("\n".join(out))

    @on(Button.Pressed, "#cfg-fill")
    def _fill(self):
        added = fill_missing()
        self.call_later(self._refill)
        self.say(f"added {len(added)} missing key(s): {', '.join(added)}" if added else "nothing was missing")

    @on(Button.Pressed, "#cfg-undo")
    def _undo(self):
        path = find_config()
        if path is None or not backup.restore(path):
            self.say("there's no earlier version to go back to")
            return
        self.call_later(self._refill)
        self.say("[#87d787]went back to the version before the last change[/]   [#9db0e0](press again to redo it)[/]")


def _lines():
    from ...config import raw_lines

    return raw_lines()
