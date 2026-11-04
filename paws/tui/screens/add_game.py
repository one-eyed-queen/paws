from __future__ import annotations

import html
import re
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Static

from ... import games
from ... import manifest
from ... import sources
from ...sls.archive import is_archive
from ...sources.store import app_kind, with_kind
from ..widgets import hires
from ..widgets.header import AppHeader
from ..widgets.modals import ModalInfo, ModalInput

DETAIL_COLS = 34
DETAIL_MIN_WIDTH = 110  # below this the results and to-add columns need the room more than the detail panel does


def _plain(text: str) -> str:
    """store text can carry html entities and the odd tag"""
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


class AddGameScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("space", "toggle_row", "toggle selected row")]

    def on_resize(self, event=None):
        try:
            self.query_one("#add-detail").display = self.size.width >= DETAIL_MIN_WIDTH
        except Exception:
            pass

    def background_cols(self):
        # keep the wallpaper off the detail panel so its real-graphics picture doesn't have
        # to share screen space with another kitty image underneath it
        try:
            if not self.query_one("#add-detail").display:
                return None  # no picture panel at this width, so the wallpaper gets the whole screen
            return self.query_one("#add-queue-col").region.right
        except Exception:
            return None

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
            with Vertical(id="add-queue-col"):
                yield Static("to add", id="add-queue-title")
                yield DataTable(id="queue-table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="add-detail", classes="panel"):
                yield Static("", id="detail-info")
                if hires.available():
                    self._img_widget = hires.picture(None, id="detail-img")
                    self._img_widget.styles.width = DETAIL_COLS
                    self._img_widget.styles.height = "auto"
                    yield self._img_widget
                else:
                    self._img_widget = None
                    yield Static("", id="detail-img")
                yield Static("", id="detail-desc", markup=False)
        with Horizontal(id="add-buttons"):
            yield Button("Add to list", id="b-add", variant="primary")
            yield Button("Apply", id="b-apply")
            yield Button("Back", id="b-back")

    def on_mount(self):
        self.query_one("#add-detail").can_focus = False
        self._table().add_columns("appid", "name", "source", "price")
        self.query_one("#queue-table", DataTable).add_columns("appid", "name")
        self._queue: list = []
        self._search_id = 0
        self._infos: dict = {}
        self._results: list = []
        self._detail: object | None = None
        self._detail_timer = None
        self._img_key = None
        self._pending_url = ""
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
            t.add_row(str(r.appid), with_kind(r.name or str(r.appid), r.kind), r.source, price)
        self.set_hint(f"{len(results)} result(s). Arrow keys to browse, Enter puts one on the list, Apply adds them.")
        if results:
            t.focus()
        self._search_id += 1
        self._load_kinds(self._search_id, results)

    @work(thread=True, exclusive=True, group="add-kinds")
    def _load_kinds(self, search_id, results):
        """search hits don't say what they are and asking is one request each, so the brackets fill in behind the list"""
        from ...sources.base import SourceError

        for row, r in enumerate(results):
            if r.kind or r.source != "store" or search_id != self._search_id:
                continue
            try:
                kind = app_kind(r.appid, r.name)
            except (OSError, ValueError, SourceError):
                continue
            if kind:
                self.app.call_from_thread(self._show_kind, search_id, row, r, kind)

    def _show_kind(self, search_id, row, r, kind):
        if search_id == self._search_id:
            r.kind = kind
            self._table().update_cell_at((row, 1), with_kind(r.name, kind))

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
                if gi.free:
                    self._free_popup(gi.name, gi.appid)
                    return
                self._show_results([gi])
            else:
                hits = sources.search_store(q)
                free = sources.free_ids([h.appid for h in hits])
                hits = [h for h in hits if h.appid not in free]
                if not hits:
                    self.set_hint(
                        f"[#9db0e0]only free stuff matched ({len(free)} hidden), free items don't need adding[/]"
                        if free
                        else "[#9db0e0]no store hits; maybe try an AppId[/]"
                    )
                    return
                self._show_results(hits)
                if free:
                    self.set_hint(f"{len(hits)} result(s), {len(free)} free one(s) hidden. Enter puts one on the list.")
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
            if not self._offer(games.plan_from_info(info)):
                return
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
        # a lone .key (or any file with no AppId of its own) needs to know what game it's
        # for - if one's already typed in the search box, use it, so the game itself gets
        # added too instead of only the file's own (appid-less) data landing somewhere
        typed = self.query_one("#in-query", Input).value.strip()
        hint_appid = int(typed) if typed.isdigit() else None
        try:
            b = manifest.ManifestBundle(appid=hint_appid)
            if is_archive(path):
                b.add_archive(path, Path.home() / ".cache" / "paws")
            else:
                b.add_file(path)
            plan = games.plan_from_bundle(b)  # finds the game itself when the file only names a depot
        except Exception as e:
            self.set_hint(f"[red]{path.name}: {e}[/red]")
            return
        if not plan.appid:
            self.set_hint(
                f"[red]couldn't tell which game {path.name} is for[/red] - drop its matching .lua "
                "alongside it, or a .zip with both, or type the AppId and search first."
            )
            return
        self.query_one("#in-query", Input).value = plan.appid
        self._offer(plan)

    @on(DataTable.RowSelected)
    def _on_row(self, ev):
        ev.stop()
        i = ev.data_table.get_row_index(ev.row_key)
        if ev.data_table.id == "queue-table":
            self._unqueue(i)
        elif 0 <= i < len(self._results):
            self._cancel_detail_timer()
            self._inspect(self._results[i])
            self._add_selected()

    @on(DataTable.RowHighlighted)
    def _on_hi(self, ev):
        if ev.data_table.id == "results-table" and ev.cursor_row is not None and 0 <= ev.cursor_row < len(self._results):
            r = self._results[ev.cursor_row]
            self._cancel_detail_timer()
            self._detail_timer = self.set_timer(0.15, lambda: self._inspect_later(r))

    def _cancel_detail_timer(self):
        if self._detail_timer is not None:
            self._detail_timer.stop()
            self._detail_timer = None

    @work(thread=True, exclusive=True, group="add-inspect")
    def _inspect_later(self, r):
        """the store answer takes a moment, and arrowing down a list shouldn't stutter on every row"""
        info = self._full_info(r)
        self.app.call_from_thread(self._show_info, r, info)

    def _show_info(self, r, info):
        table = self._table()
        if table.cursor_row < len(self._results) and self._results[table.cursor_row] is r:
            self._show_detail(info)

    def _full_info(self, r):
        if r.source != "store":
            return r
        if r.appid not in self._infos:
            try:
                self._infos[r.appid] = sources.from_store(r.appid)
            except Exception:
                return r
        return self._infos[r.appid]

    def _inspect(self, r):
        self._show_detail(self._full_info(r))

    def _show_detail(self, gi):
        self._detail = gi
        title = f"[b]{gi.appid}[/b]  {with_kind(gi.name, gi.kind)}" if gi.name else f"[b]{gi.appid}[/b]"
        price = "[green]free[/green]" if gi.free else f"[green]{gi.price}[/green]" if gi.price else ""
        self.set_detail(f"{title}\n{price}" if price else title)
        self._show_image(getattr(gi, "header_image", "") or "")
        self.query_one("#detail-desc", Static).update(_plain(gi.short_description))

    def _show_image(self, url):
        from .. import imgpreview

        if self._img_widget is None:
            self.set_image((imgpreview.cached_build(url, 34) or "") if url else "")
            return
        # let the widget open and fit the file itself (styles.width fixed, height "auto") -
        # building our own pixel-perfect canvas here was the source of three separate bugs
        self._pending_url = url
        self.call_after_refresh(self._apply_image, url)

    def _apply_image(self, url):
        from .. import imgpreview

        if url != self._pending_url:
            return  # superseded by a newer selection while this was waiting to apply
        path = imgpreview.cached_path(url) if url else None
        if path == self._img_key:
            return
        self._img_key = path
        self._img_widget.image = path

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
            self._offer(games.plan_from_info(info), info.kind)
        except Exception as e:
            self.set_hint(f"[red]{e}[/red]")

    def _free_popup(self, name, appid):
        self.app.push_screen(ModalInfo(games.free_message(name, str(appid)), "free on steam"))
        self.set_hint(f"[#ffb454]{name or appid} is free, nothing added[/]")

    def _offer(self, plan, kind="") -> bool:
        """onto the to-add list, leaving the search and its results where they are so the next game is one key away.
        free things never get there: the item itself gets a popup, free dlc / linked apps just drop out"""
        item_is_free, extras = games.strip_free(plan)
        if item_is_free:
            self._free_popup(plan.name, plan.appid)
            return False
        label = with_kind(plan.name or plan.appid, kind)
        if any(queued.appid == plan.appid for queued, _ in self._queue):
            self.set_hint(f"[#9db0e0]{label} is already on the list[/]")
            return False
        self._queue.append((plan, label))
        self._draw_queue()
        left_out = f", {len(extras)} free extra(s) left out" if extras else ""
        self.set_hint(f"{label} on the list{left_out}. Apply adds {len(self._queue)} game(s).")
        return True

    def _draw_queue(self):
        table = self.query_one("#queue-table", DataTable)
        table.clear()
        for plan, label in self._queue:
            table.add_row(plan.appid, label)
        self.query_one("#add-queue-title", Static).update(f"to add ({len(self._queue)})" if self._queue else "to add")

    def _unqueue(self, i):
        if 0 <= i < len(self._queue):
            _plan, label = self._queue.pop(i)
            self._draw_queue()
            self.set_hint(f"{label} off the list")

    def action_toggle_row(self):
        table = self.query_one("#queue-table", DataTable)
        if table.has_focus and table.row_count:
            self._unqueue(table.cursor_row)

    def _apply(self):
        if not self._queue:
            self.set_hint("[#9db0e0]nothing on the list yet: Enter on a result puts it there[/]")
            return
        names = [label for _plan, label in self._queue]
        try:
            result = games.apply_bulk([plan for plan, _label in self._queue])
        except Exception as e:  # the list stays, so nothing has to be picked again
            self.set_hint(f"[red]{e}[/red]")
            return
        self._queue = []
        self._draw_queue()
        self.set_hint(f"[green]added {len(names)} game(s)[/green] [red]errors={len(result['errors'])}[/red]")
        if result["errors"]:
            self.app.tell(f"added {len(names)} game(s), with problems", str(result["errors"][0])[:160], "warning")
        else:
            self.app.tell(f"added {len(names)} game(s)", ", ".join(names)[:160])

    def action_pop(self):
        self.app.pop_screen()
