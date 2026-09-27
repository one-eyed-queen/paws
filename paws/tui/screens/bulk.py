from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static, TextArea

from ... import games
from ...textdrop import Parsed, parse_text
from ..widgets.header import AppHeader
from ..widgets.modals import Confirm

HINT = (
    "paste ids, links or a whole dlc page (open the app's DLC page, ctrl+a, ctrl+c, paste here)\n"
    "one per line is fine; names, dates and types beside the ids are read too"
)


class BulkScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Bulk add / remove", id="hdr")
        yield TextArea(id="bulk-text")
        yield DataTable(id="bulk-table", cursor_type="row", zebra_stripes=True)
        yield Static(f"[#9db0e0]{HINT}[/]", id="bulk-out", classes="panel")
        with Horizontal(id="bulk-buttons"):
            yield Button("Add all", variant="primary", id="b-bulk-add")
            yield Button("Remove all", id="b-bulk-remove")
            yield Button("Look up names", id="b-bulk-names")
            yield Button("Clear", id="b-bulk-clear")
            yield Button("Back", id="b-bulk-back")

    def on_mount(self):
        self.parsed = Parsed()
        self.names: dict[str, str] = {}
        self.query_one("#bulk-table", DataTable).add_columns("id", "name", "what")
        self.query_one("#bulk-text", TextArea).focus()

    @on(TextArea.Changed)
    def _changed(self, ev):
        self.parsed = parse_text(ev.text_area.text)
        self._show()

    def _show(self):
        t = self.query_one("#bulk-table", DataTable)
        t.clear()
        p = self.parsed
        for it in p.items:
            t.add_row(it.id, it.name or self.names.get(it.id, "") or "[#9db0e0]?[/]", it.note or "app")
        if p.kind == "depots":
            self.set_out("[yellow]that's a depot list: those ids aren't apps, nothing to add[/yellow]")
        elif p.items:
            base = f" of [b]{p.base_name or p.base_id}[/b]" if p.kind == "dlc" and p.base_id else ""
            self.set_out(
                f"[b]{len(p.items)}[/b] app id(s) found{base}. Add all writes them (with a comment beside each)."
            )
        else:
            self.set_out(f"[#9db0e0]{HINT}[/]")

    def set_out(self, text: str):
        self.query_one("#bulk-out", Static).update(text)

    @on(Button.Pressed, "#b-bulk-add")
    def _add(self):
        if not self.parsed.items:
            self.set_out("[yellow]nothing to add yet: paste some ids first[/yellow]")
            return
        result = games.apply_bulk(games.plans_from(self.parsed, self.names))
        new = result["added"]
        text = (
            f"[green]added {new} new entr{'y' if new == 1 else 'ies'}[/green] for {result['games']} game(s)"
            if new
            else "[yellow]nothing new: all of it was already in your config[/yellow]"
        )
        if result["errors"]:
            text += f"\n[red]{len(result['errors'])} error(s)[/red]: {result['errors'][0]}"
        self.set_out(text)
        self.app.tell(
            f"bulk add: {new} new", f"{result['games']} game(s)", "warning" if result["errors"] else "information"
        )

    @on(Button.Pressed, "#b-bulk-remove")
    def _remove(self):
        ids = self._ids_to_remove()
        if not ids:
            self.set_out("[yellow]nothing to remove yet: paste some ids first[/yellow]")
            return
        what = (
            f"the game {ids[0]} and all its DLC"
            if self.parsed.kind == "dlc" and self.parsed.base_id
            else f"{len(ids)} app(s)"
        )
        self.app.push_screen(
            Confirm(f"Remove {what}?\n(only what paws added is taken out)", dangerous=True),
            lambda yes: self._remove_now(ids) if yes else None,
        )

    def _ids_to_remove(self):
        p = self.parsed
        if p.kind == "dlc" and p.base_id:
            return [p.base_id]
        return list(dict.fromkeys(p.ids))

    def _remove_now(self, ids):
        result = games.remove_bulk(ids)
        self.set_out(
            f"[green]removed {result['removed']} thing(s)[/green] from {result['removed_games']} game(s)"
            + (f", {result['not_found']} weren't there" if result["not_found"] else "")
        )
        self.app.tell("bulk remove", f"{result['removed']} thing(s) from {result['removed_games']} game(s)")

    @on(Button.Pressed, "#b-bulk-names")
    def _names(self):
        ids = [i.id for i in self.parsed.items if not i.name and i.id not in self.names]
        if not ids:
            self.set_out("every id already has a name")
            return
        self.set_out(f"looking up {len(ids)} name(s) on the store...")
        self._lookup(ids)

    @work(thread=True, exclusive=True, group="bulk-names")
    def _lookup(self, ids):
        found = games.lookup_names(ids)
        self.app.call_from_thread(self._got_names, found, len(ids))

    def _got_names(self, found, asked):
        self.names.update(found)
        self._show()
        self.set_out(f"found {len(found)} of {asked} name(s)")

    @on(Button.Pressed, "#b-bulk-clear")
    def _clear(self):
        self.query_one("#bulk-text", TextArea).clear()
        self.names.clear()

    @on(Button.Pressed, "#b-bulk-back")
    def _back(self):
        self.action_pop()

    def action_pop(self):
        self.app.pop_screen()
