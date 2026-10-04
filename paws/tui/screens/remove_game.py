from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Static

from ... import games
from ..widgets.header import AppHeader
from ..widgets.modals import Confirm


class RemoveGameScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Remove a game", id="hdr")
        with Horizontal(id="rm-search"):
            yield Input(placeholder="search by name or AppId (blank shows everything)", id="in-rid")
            yield Button("Search", id="b-rm-search")
        yield DataTable(id="rm-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="remove-actions"):
            yield Button("Preview + Remove", id="b-preview")
            yield Button("Refresh", id="b-refresh")
            yield Button("Bulk...", id="b-bulk")
        yield Static("", id="remove-out", classes="panel")

    def on_mount(self):
        self._selected: tuple[str, str, str | None] | None = None
        self.query_one("#rm-table", DataTable).add_columns("id", "name", "kind")
        self._refresh_table()
        if not self.query_one("#rm-table", DataTable).row_count:
            self.set_out("[#9db0e0]nothing added yet[/]")
        self.query_one("#in-rid", Input).focus()

    def _refresh_table(self, query: str = ""):
        table = self.query_one("#rm-table", DataTable)
        table.clear()
        q = query.strip().lower()
        shown = 0
        for g in games.list_added_games():
            appid, name = g["appid"], g["name"]
            dlc = list(g["dlc"].items())
            if (
                q
                and q not in appid.lower()
                and q not in name.lower()
                and not any(q in d.lower() or q in n.lower() for d, n in dlc)
            ):
                continue
            shown += 1
            table.add_row(appid, name or "[#9db0e0]?[/]", "game", key=f"game:{appid}")
            for dlc_id, dlc_name in dlc:
                table.add_row(f"  └ {dlc_id}", dlc_name or "[#9db0e0]?[/]", "dlc", key=f"dlc:{appid}:{dlc_id}")
        if q:
            self.set_out(
                f'{shown} match(es) for "{query.strip()}"' if shown else f'[#9db0e0]no match for "{query.strip()}"[/]'
            )

    def set_out(self, text: str):
        self.query_one("#remove-out", Static).update(text)

    @on(Button.Pressed, "#b-refresh")
    def _refresh(self):
        self.query_one("#in-rid", Input).value = ""
        self._refresh_table()

    @on(Button.Pressed, "#b-rm-search")
    def _search(self):
        self._refresh_table(self.query_one("#in-rid", Input).value)

    @on(Input.Submitted, "#in-rid")
    def _search_submit(self):
        self._search()

    @on(DataTable.RowSelected, "#rm-table")
    def _row_selected(self, ev: DataTable.RowSelected):
        raw = str(ev.row_key.value)
        if raw.startswith("game:"):
            self._selected = ("game", raw.partition(":")[2], None)
        elif raw.startswith("dlc:"):
            _, base, dlc_id = raw.split(":", 2)
            self._selected = ("dlc", base, dlc_id)
        self._preview()

    @on(Button.Pressed, "#b-bulk")
    def _bulk(self):
        from .bulk import BulkScreen

        self.app.push_screen(BulkScreen())

    @on(Button.Pressed, "#b-preview")
    def _preview_button(self):
        typed = self.query_one("#in-rid", Input).value.strip()
        if typed.isdigit():
            self._selected = ("game", typed, None)
        self._preview()

    def _preview(self):
        if not self._selected:
            self.set_out("[yellow]pick a row, or type an AppId first[/yellow]")
            return
        kind, appid, dlc_id = self._selected
        if kind == "dlc":
            self.set_out(f"will remove DLC {dlc_id} from {appid} (the base game and its other DLC stay)\n\nproceed?")
            self.app.push_screen(Confirm(f"Remove DLC {dlc_id}?", dangerous=True), self._do_remove)
        else:
            plan = games.plan_remove(appid)
            self.set_out("will remove:\n" + "\n".join(plan.notes) + "\n\nproceed?")
            self.app.push_screen(Confirm(f"Remove all SLS entries for AppId {appid}?", dangerous=True), self._do_remove)

    def _do_remove(self, yes):
        if not yes or not self._selected:
            return
        kind, appid, dlc_id = self._selected
        if kind == "dlc":
            result = games.remove_single_dlc(appid, dlc_id)
            self.set_out(f"[green]done[/green]: {result}")
            self.app.tell(f"DLC {dlc_id} removed", f"{result.get('removed', 0)} entries taken out")
        else:
            result = games.apply_remove(games.plan_remove(appid))
            self.set_out(f"[green]done[/green]: {result}")
            self.app.tell(f"{appid} removed", f"{result.get('removed', 0)} entries taken out")
        self._selected = None
        self._refresh_table()

    def action_pop(self):
        self.app.pop_screen()
