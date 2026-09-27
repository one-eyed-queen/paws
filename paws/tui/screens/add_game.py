from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Static

from ... import games
from ... import manifest
from ... import sources
from ..widgets.header import AppHeader
from ..widgets.modals import ModalInput


class AddGameScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("space", "toggle_row", "toggle selected row")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Add a game", id="hdr")
        with Vertical(id="add-inputs"):
            yield Input(placeholder="game name or AppId (try 480, or 'counter-strike')", id="in-query")
            with Horizontal(id="add-actions"):
                yield Button("Search", variant="primary", id="b-search")
                yield Button("Parse SLS output", id="b-parse")
                yield Button("Import file", id="b-import")
                yield Button("Bulk...", id="b-bulk")
        with Horizontal(id="add-split"):
            with Vertical(id="add-left"):
                yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="add-hint", classes="panel")
            with VerticalScroll(id="add-detail", classes="panel"):
                yield Static("", id="detail-info")
                yield Static("", id="detail-img")
        with Horizontal(id="add-buttons"):
            yield Button("Add selected game", id="b-add", variant="primary")
            yield Button("Apply (checked)", id="b-apply")
            yield Button("Back", id="b-back")

    def on_mount(self):
        self.query_one("#add-detail").can_focus = False
        self._table().add_columns("appid", "name", "source", "price")
        self._plan = None
        self._checked: set[int] = set()
        self._results: list = []
        self._detail: object | None = None
        self.query_one("#in-query", Input).focus()

    @on(Button.Pressed, "#b-bulk")
    def _bulk(self):
        from .bulk import BulkScreen

        self.app.push_screen(BulkScreen())

    def _table(self):
        return self.query_one("#results-table", DataTable)

    def set_hint(self, text: str):
        self.query_one("#add-hint", Static).update(text)

    def set_detail(self, text: str):
        self.query_one("#detail-info", Static).update(text)

    def set_image(self, text: str):
        self.query_one("#detail-img", Static).update(text)

    def _show_results(self, results):
        self._results = results
        t = self._table()
        t.clear(columns=True)
        t.add_columns("appid", "name", "source", "price")
        for r in results:
            price = f"[#9db0e0]{r.price}[/]" if getattr(r, "price", "") else ""
            t.add_row(str(r.appid), r.name or str(r.appid), r.source, price)
        self.set_hint(f"{len(results)} result(s). Hover + Enter to inspect, then 'Add selected game'.")

    def on_input_submitted(self, ev: Input.Submitted):
        if ev.input is not None and ev.input.id == "in-query":
            self._search(ev.input.value)

    @on(Button.Pressed)
    def _act(self, ev):
        sid = ev.button.id
        q = self.query_one("#in-query", Input).value.strip()
        if sid == "b-search":
            self._search(q)
        elif sid == "b-parse":
            self.app.push_screen(
                ModalInput("Paste AdditionalApps: / DlcData: formatted text:"),
                self._parse_output,
            )
        elif sid == "b-import":
            self.app.push_screen(ModalInput("Drop path to a .lua/.manifest/.key/.zip"), self._import_path_input)
        elif sid == "b-add":
            self._add_selected()
        elif sid == "b-apply":
            self._apply()
        elif sid == "b-back":
            self.action_pop()

    def _search(self, q):
        if not q:
            self.set_hint("[red]type a game name or AppId first[/red]")
            return
        q = q.strip()
        try:
            if q.isdigit():
                gi = sources.from_store(q)
                self._show_results([gi])
            else:
                hits = sources.search_store(q)
                if not hits:
                    self.set_hint("[#9db0e0]no store hits; maybe try an AppId[/]")
                    return
                self._show_results(hits)
        except RuntimeError as e:
            self.set_hint(f"[red]{e}[/red]")
        except Exception as e:
            self.set_hint(f"[red]{e}[/red]")

    def _parse_output(self, text):
        if not text:
            return
        try:
            additional, dlc_data = sources.parse_sls_output(text.strip())
            if not additional and not dlc_data:
                self.set_hint("[red]nothing parseable - expected 'AdditionalApps:' / 'DlcData:'[/red]")
                return
            appid = dlc_data and next(iter(dlc_data)) or (additional[0] if additional else "")
            info = sources.GameInfo(appid=str(appid), name="from pasted output", source="pasted")
            info.linked = additional
            info.dlc_names = next(iter(dlc_data.values())) if dlc_data else {}
            self._render_plan(games.plan_from_info(info))
            self.set_detail(f"[b]{appid}[/b]  pasted output: {len(additional)} additional + {len(info.dlc_names)} dlc")
        except Exception as e:
            self.set_hint(f"[red]{e}[/red]")

    def _import_path_input(self, p):
        if p:
            self._import_path(p)

    def _import_path(self, p):
        path = Path(p.strip().strip("'\"")).expanduser()
        if not path.exists():
            self.set_hint(f"[red]not found:[/red] {path}")
            return
        b = manifest.ManifestBundle()
        if path.suffix.lower() in (".zip", ".7z"):
            b.add_archive(path, Path.home() / ".cache" / "paws")
        else:
            b.add_file(path)
        flat = b.flatten()
        appid = str(b.appid or (flat["app_ids"][0] if flat["app_ids"] else ""))
        self.query_one("#in-query", Input).value = appid
        self._render_plan(games.plan_from_bundle(b))

    @on(DataTable.RowSelected)
    def _on_row(self, ev):
        t = self._table()
        i = t.get_row_index(ev.row_key)
        if self._plan is not None:
            (self._checked.discard if i in self._checked else self._checked.add)(i)
            self._draw()
        elif 0 <= i < len(self._results):
            self._inspect(self._results[i])
        ev.stop()

    @on(DataTable.RowHighlighted)
    def _on_hi(self, ev):
        if self._plan is None and ev.cursor_row is not None and 0 <= ev.cursor_row < len(self._results):
            self._inspect(self._results[ev.cursor_row])

    def _inspect(self, r):
        try:
            gi = sources.from_store(r.appid) if r.source == "store" else r
        except Exception:
            gi = r
        self._detail = gi
        box = f"[b]{gi.appid}[/b]  {gi.name}" if gi.name else f"[b]{gi.appid}[/b]"
        metadata = []
        if gi.developers:
            metadata.append(f"[#9db0e0]by[/] {', '.join(gi.developers[:3])}")
        if gi.price or gi.free:
            metadata.append("[green]free[/green]" if gi.free else f"[green]{gi.price}[/green]")
        metadata.append(f"[#9db0e0]{len(gi.dlcs)} dlc(s), {len(gi.packages)} package(s)[/]")
        desc = gi.short_description or gi.about or "no description from this source - use Search to pull store text."
        desc = "\n".join(f"  {line}" for line in desc.splitlines()[:20])
        self.set_detail(f"{box}\n   ┊ {'  ·  '.join(metadata)}\n\n{desc}")
        image = getattr(gi, "header_image", "") or ""
        if image:
            from .. import imgpreview

            art = imgpreview.cached_build(image, 40)
            self.set_image(art or "[#9db0e0](image unavailable)[/]")

    def _add_selected(self):
        if self._detail is None and self._results:
            self._detail = self._results[0]
        if self._detail is None:
            self.set_hint("[red]hover / select a result first[/red]")
            return
        info = self._detail
        try:
            if not getattr(info, "depot_keys", None) and info.appid.isdigit():
                info = sources.from_store(info.appid)
            self._render_plan(games.plan_from_info(info))
            self.set_hint("plan ready - review the checklist, then Apply (checked).")
        except Exception as e:
            self.set_hint(f"[red]{e}[/red]")

    def _render_plan(self, plan):
        self._plan = plan
        self._checked = set(range(len(plan.changes())))
        self._draw()

    def _draw(self):
        t = self._table()
        t.clear(columns=True)
        t.add_columns("apply", "where", "what", "detail")
        if self._plan:
            for i, c in enumerate(self._plan.changes()):
                mark = "[green]ON[/green]" if i in self._checked else "[#9db0e0]--[/]"
                t.add_row(mark, c.target, c.action, c.detail)
            self.set_hint(f"[#9db0e0]space toggles a row; Enter applies. Plan: {self._plan.counts()}[/]")

    def action_toggle_row(self):
        t = self._table()
        if t.cursor_row is not None and t.row_count and self._plan is not None:
            i = t.cursor_row
            (self._checked.discard if i in self._checked else self._checked.add)(i)
            self._draw()

    def _apply(self):
        if not self._plan:
            return
        changes = self._plan.changes()
        checked = {changes[i].key for i in self._checked}
        result = games.apply_plan(self._plan, checked=checked)
        self.set_hint(f"[green]applied {result['applied']}[/green] [red]errors={len(result['errors'])}[/red]")
        name = self._plan.name or self._plan.appid
        if result["errors"]:
            self.app.tell(
                f"{name}: {result['applied']} applied, {len(result['errors'])} failed",
                str(result["errors"][0])[:160],
                "warning",
            )
        else:
            self.app.tell(f"{name} added", f"{result['applied']} changes applied")

    def action_pop(self):
        self.app.pop_screen()
