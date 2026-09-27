from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from ... import repair
from ...config.where import find_config
from ...paths import default_config_dir
from ...util import backup
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar
from ..widgets.modals import Confirm


class RepairScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Repair", id="hdr")
        yield DataTable(id="repair-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="repair-out", classes="panel")
        yield JobBar(id="job")
        with Horizontal(id="repair-buttons"):
            yield Button("Fix selected", variant="primary", id="b-fix-one")
            yield Button("Fix all", id="b-fix-all")
            yield Button("Restore config backup", id="b-restore")
            yield Button("Re-scan", id="b-scan")
            yield Button("Back", id="b-back")

    def on_mount(self):
        t = self.query_one("#repair-table", DataTable)
        t.add_columns("problem", "fixable")
        self.scan()

    def scan(self, message: str = ""):
        self.problems = repair.scan()
        t = self.query_one("#repair-table", DataTable)
        t.clear()
        for p in self.problems:
            t.add_row(p.title, "yes" if p.fixable else "no", key=p.id)
        if self.problems:
            t.focus()
            self._describe(0)
        else:
            self.set_out((message + "\n" if message else "") + "[green]nothing is broken[/green]")

    def set_out(self, text: str):
        self.query_one("#repair-out", Static).update(text)

    def _describe(self, row):
        if 0 <= row < len(self.problems):
            p = self.problems[row]
            self.set_out(f"[b]{p.title}[/b]\n{p.detail}\n[#9db0e0]fix: {p.fix_note or 'none automatic'}[/]")

    @on(DataTable.RowHighlighted)
    def _hi(self, ev):
        self._describe(ev.cursor_row)

    def _selected(self):
        t = self.query_one("#repair-table", DataTable)
        row = t.cursor_row
        return self.problems[row] if self.problems and 0 <= row < len(self.problems) else None

    @on(Button.Pressed, "#b-fix-one")
    def _fix_one(self):
        p = self._selected()
        if p is None:
            return
        if not p.fixable:
            self.set_out(f"[yellow]no automatic fix for:[/yellow] {p.title}")
            return
        self.app.push_screen(Confirm(f"{p.title}\n\n{p.fix_note}?"), lambda yes, p=p: self._do([p]) if yes else None)

    @on(Button.Pressed, "#b-fix-all")
    def _fix_all(self):
        todo = [p for p in self.problems if p.fixable]
        if not todo:
            self.set_out("nothing to fix automatically")
            return
        self.app.push_screen(
            Confirm(f"Fix {len(todo)} thing(s)?\n\n" + "\n".join(f"- {p.fix_note}" for p in todo)),
            lambda yes: self._do(todo) if yes else None,
        )

    def _do(self, todo):
        self.app.run_job("fixing", lambda progress: repair.apply_all(todo), self._fixed)

    def _fixed(self, results):
        if isinstance(results, Exception):
            self.app.tell("couldn't fix it", str(results), "error")
            return
        lines = [f"{'[green]fixed[/green]' if ok else '[red]failed[/red]'}: {note}" for _, ok, note in results]
        bad = sum(not ok for _, ok, _ in results)
        self.app.tell(
            f"repaired {len(results) - bad} thing(s)" + (f", {bad} failed" if bad else ""),
            "",
            "warning" if bad else "information",
        )
        if not self.is_attached:
            return
        self.scan()
        left = (
            f"\n\n[#9db0e0]still to look at: {len(self.problems)}[/]"
            if self.problems
            else "\n\n[green]nothing is broken[/green]"
        )
        self.set_out("\n".join(lines) + left)

    @on(Button.Pressed, "#b-restore")
    def _restore(self):
        config_path = find_config() or default_config_dir() / "config.yaml"
        versions = backup.versions_of(config_path.name)
        if not versions:
            self.set_out("[yellow]no config.yaml backups yet[/yellow] (they're made the first time paws changes it)")
            return
        newest = versions[0]
        self.app.push_screen(
            Confirm(f"Put back {newest.name} as your config.yaml?\n(the current one is backed up first)"),
            lambda yes: self._restore_now(newest, config_path) if yes else None,
        )

    def _restore_now(self, newest, config_path):
        ok = backup.restore_backup(newest, config_path)
        self.scan(f"[green]restored {newest.name}[/green]" if ok else "[red]restore failed[/red]")

    @on(Button.Pressed, "#b-scan")
    def _rescan(self):
        self.scan()

    @on(Button.Pressed, "#b-back")
    def _back(self):
        self.action_pop()

    def action_pop(self):
        self.app.pop_screen()
