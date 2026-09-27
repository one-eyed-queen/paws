from __future__ import annotations

import time

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, RadioButton, RadioSet, Static, TabbedContent, TabPane

from ...sls import activation
from ...sls import encode as encode_mod
from ...sls import tickets
from ...util import clipboard
from ..widgets.footer import FooterHelp
from ..widgets.header import AppHeader
from ..widgets.modals import Confirm, ModalInfo, ModalInput, ModalPaste

KINDS = (
    ("both", "Both tickets"),
    ("encrypted", "Encrypted only"),
    ("normal", "Normal only"),
)


HOW = (
    "[b #ffffff]what Make tickets does[/]\n\n"
    "[#9db0e0]1[/]  puts the AppId in AdditionalApps in your config.yaml (backs it up first)\n"
    "[#9db0e0]2[/]  runs the game once through SLSsteam. if the SLSsteam API is on it just asks the running steam,\n"
    "    if not it restarts steam once (never behind your back) and leaves it running with SLSsteam loaded\n"
    "[#9db0e0]3[/]  SLSsteam saves the tickets in its cache, paws shows what showed up\n\n"
    "[#9db0e0]both tickets[/] = the encrypted one and the normal ownership one. the encrypted one only shows up\n"
    "while the game is really running and asks for it, so if you only got the ownership one the game never got\n"
    "that far. run it once and the file appears. the Use tab lists them, copies them, and takes one back from a\n"
    "paste or a ticket file dropped on the window"
)


class ActivationScreen(Screen):
    DEFAULT_CLASSES = "page"
    _found: list = []

    BINDINGS = [
        Binding("escape", "pop", "back"),
        Binding("backspace", "pop", "back", show=False),
        Binding("alt+1", "tab('make')", "make", show=False),
        Binding("alt+2", "tab('use')", "use", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader("Activation", id="hdr")
        with TabbedContent(initial="make", id="act-tabs"):
            with TabPane("Make tickets", id="make"):
                with Vertical(id="act-make"):
                    yield Static(
                        "[#9db0e0]runs the game once through SLSsteam so it caches its tickets: the encrypted one and the normal ownership one[/]",
                        id="act-blurb",
                    )
                    with Horizontal(id="act-top"):
                        yield Input(placeholder="AppId (e.g. 480)", id="in-aid")
                        yield Button("Make tickets", id="b-act-go", variant="primary")
                    with RadioSet(id="act-kind"):
                        for i, (_, label) in enumerate(KINDS):
                            yield RadioButton(label, value=i == 0)
                    yield Static(HOW, id="act-how", classes="panel", markup=True)
            with TabPane("Use tickets", id="use"):
                with Vertical(id="act-use"):
                    with Horizontal(id="act-split"):
                        yield DataTable(id="tick-table", cursor_type="row", zebra_stripes=True)
                        yield Static("", id="tick-info", classes="panel", markup=True)
                    with Grid(id="act-actions-use"):
                        yield Button("Use selected", id="b-use", variant="primary")
                        yield Button("Paste", id="b-imp")
                        yield Button("Copy", id="b-copy")
                        yield Button("Delete", id="b-del")
                        yield Button("Backup", id="b-pack")
                        yield Button("Restore", id="b-unpack")
                        yield Button("Details", id="b-detail")
        yield Static("", id="act-out", classes="panel")
        yield FooterHelp("alt+1 make · alt+2 use · paste or drop a ticket file to import it · esc back")

    def on_mount(self):
        self.query_one("#in-aid", Input).focus()
        self._draw_tickets()

    def on_screen_resume(self):
        self._draw_tickets(keep_message=True)

    def on_resize(self, event):
        self.query_one("#tick-info").display = self.size.width >= 100

    @on(DataTable.RowHighlighted, "#tick-table")
    def _row_moved(self, ev):
        self._show_info()

    def _show_info(self):
        info = self.query_one("#tick-info", Static)
        found = self._found
        rk = self._table().cursor_row
        if not found or rk is None or rk >= len(found):
            info.update(
                "[#9db0e0]nothing picked[/]\n\n[#9db0e0]make tickets on the first tab, or paste / drop a ticket file here[/]"
            )
            return
        tk = found[rk]
        kind = "encrypted ticket" if tk.encrypted else "normal ownership ticket"
        info.update(
            f"[b #ffffff]{tk.appid}[/]   [#9db0e0]{kind}[/]\n\n"
            f"[#9db0e0]steamId[/]  {tk.steam_id}\n"
            f"[#9db0e0]size[/]     {tk.size} bytes\n"
            f"[#9db0e0]file[/]     {tk.filename}\n"
            f"[#9db0e0]saved in[/] {tk.path.parent if tk.path else '?'}\n\n"
            "[#9db0e0]Copy puts the file text on your clipboard, Paste adds one back[/]"
        )

    @on(TabbedContent.TabActivated)
    def _tab_changed(self, ev):
        pane = ev.pane.id
        if pane == "make":
            self.query_one("#in-aid", Input).focus()
        elif pane == "use":
            self._table().focus()

    def _table(self):
        return self.query_one("#tick-table", DataTable)

    def set_out(self, text: str):
        self.query_one("#act-out", Static).update(text)

    def action_tab(self, name: str):
        self.query_one("#act-tabs", TabbedContent).active = name

    def _kind(self):
        i = self.query_one("#act-kind", RadioSet).pressed_index
        return KINDS[i if i >= 0 else 0][0]

    def _draw_tickets(self, keep_message=False):
        t = self._table()
        t.clear(columns=True)
        t.add_columns("appid", "kind", "steamId", "size")
        found = self._found = tickets.list_tickets()
        for tk in found:
            t.add_row(tk.appid, "encrypted" if tk.encrypted else "normal", tk.steam_id, str(tk.size))
        if not keep_message:
            self.set_out(
                f"{len(found)} tickets in the cache" if found else "no tickets in the cache yet: make one first"
            )
        self._show_info()

    def _selected(self):
        t = self._table()
        rk = t.cursor_row
        found = self._found
        if rk is None or not t.row_count or rk >= len(found):
            self.set_out("pick a ticket in the list first")
            return None
        return found[rk]

    @on(Button.Pressed)
    def _pressed(self, ev):
        sid = ev.button.id
        if sid == "b-act-go":
            appid = self.query_one("#in-aid", Input).value.strip()
            if not appid.isdigit():
                self.set_out("[red]type the game's AppId (numbers only)[/red]")
                return
            self.set_out("working: making the ticket (this can take a minute)...")
            self._activate(appid, self._kind())
        elif sid == "b-imp":
            self._import_pressed()
        elif sid == "b-copy":
            self._copy_selected()
        elif sid == "b-pack":
            self._pack_selected()
        elif sid == "b-unpack":
            self.app.push_screen(
                ModalInput("Paste the paw1e string (your own backup)", "Restore pair"), self._restore_tickets
            )
        elif sid == "b-detail":
            self._detail_selected()
        elif sid == "b-use":
            self._use_selected()
        elif sid == "b-del":
            self._delete_selected()

    @on(Input.Submitted, "#in-aid")
    def _submit(self):
        self.query_one("#b-act-go", Button).press()

    @work(thread=True, exclusive=True, group="activate")
    def _activate(self, appid, want):
        started = time.monotonic()
        r = activation.activate(appid, want=want)
        self.app.call_from_thread(self._activated, appid, r, time.monotonic() - started)

    def _activated(self, appid, r, took):
        self._draw_tickets(keep_message=True)
        made_tickets = r["tickets"]
        if r["error"] or not made_tickets:
            why = str(r["error"] or "no tickets came back")
            self.set_out(f"[red]no tickets for {appid}: {why}[/red]")
            self.app.tell(f"ticket for {appid} failed", why[:200], "error", took=took)
            self.app.push_screen(
                ModalInfo(
                    f"{why}\n\nmethod: {r['method'] or 'none'}\nnothing was written", f"tickets for {appid} failed"
                )
            )
            return
        lines = []
        for t in made_tickets:
            lines += [
                t.filename,
                f"  {'encrypted ticket' if t.encrypted else 'normal ownership ticket'}, {t.size} bytes",
                f"  steamId {t.steam_id}",
                f"  in {t.path}",
                "",
            ]
        lines += [
            f"made with the {r['method']} method in {took:.0f}s",
            "copied to the clipboard" if r["copied"] else "not copied (Copy on the Use tab does it)",
        ]
        want = r.get("want", "both")
        enc_missing = f"encryptedTicket_{appid}.yaml" in (r.get("missing") or [])
        if want != "normal" and enc_missing:
            lines += [
                "",
                "[b #ffb454]the encrypted ticket didn't land[/]",
                (
                    "SLSsteam only saves it while the game itself is running and asking for one. "
                    "if this game uses an encrypted ticket, launch it once through paws / SLSsteam "
                    "(it's already in your config) and the file will show up in the Use tab."
                ),
            ]
            self.set_out(
                f"[#ffb454]{appid}: ownership ticket done, encrypted ticket missing[/] - run the game once and it appears"
            )
            self.app.tell(
                f"{appid} ready (encrypted missing)",
                "SLSsteam only writes the encrypted ticket while the game runs and asks for it",
                "error",
                took=took,
            )
        else:
            self.set_out(f"tickets for {appid} ready: {', '.join(t.base for t in made_tickets)}")
            self.app.tell(f"tickets for {appid} ready", "copied to the clipboard" if r["copied"] else "", took=took)
        self.app.push_screen(
            ModalInfo("\n".join(lines), f"tickets for {appid} ready", copy=tickets.to_clipboard_text(made_tickets[0]))
        )

    def _use_selected(self):
        tk = self._selected()
        if tk is None:
            return
        try:
            activation.ensure_subscribed(tk.appid)
        except Exception as e:
            self.set_out(f"[red]couldn't set {tk.appid} up: {e}[/red]")
            return
        self.set_out(
            f"{tk.filename} is in the cache and {tk.appid} is in your config: SLSsteam loads the ticket when the game starts"
        )
        self.app.tell(f"{tk.appid} ready to use", tk.filename)

    def _import_pressed(self):
        self.app.push_screen(
            ModalPaste(
                "paste the ticket file text here (steamId + ticket or encryptedTicket), then Import", "Paste a ticket"
            ),
            self._got_yaml,
        )

    @staticmethod
    def looks_like_ticket(text: str) -> bool:
        return "steamId:" in text and ("ticket:" in text or "encryptedTicket:" in text) and len(text) < 64 * 1024

    def take_pasted(self, text: str) -> bool:
        if not self.looks_like_ticket(text):
            return False
        self._got_yaml(text)
        return True

    def _got_yaml(self, text):
        if not text or not text.strip():
            return
        appid = self.query_one("#in-aid", Input).value.strip()
        if appid.isdigit():
            self._save_yaml(appid, text)
            return
        self._yaml_waiting = text
        self.app.push_screen(ModalInput("Which AppId is this ticket for? (e.g. 480)", "AppId"), self._got_appid)

    def _got_appid(self, appid):
        if appid and appid.strip().isdigit():
            self._save_yaml(appid.strip(), self._yaml_waiting)
        elif appid:
            self.set_out("[red]the AppId is just numbers[/red]")

    def _save_yaml(self, appid, text):
        try:
            tk = tickets.save_ticket(appid, text.strip())
        except ValueError as e:
            self.set_out(f"[red]{e}[/red]")
            self.app.tell("that isn't a ticket", str(e)[:160], "error")
            return
        self.set_out(f"imported {tk.filename}")
        self.app.tell(f"imported {tk.filename}")
        self._draw_tickets(keep_message=True)
        self.action_tab("use")

    def _copy_selected(self):
        tk = self._selected()
        if tk is not None:
            ok = clipboard.copy(tickets.to_clipboard_text(tk))
            self.set_out(f"{'copied' if ok else 'copy failed'}: {tk.filename}")

    def _pack_selected(self):
        tk = self._selected()
        if tk is None:
            return
        self._pack_appid = tk.appid
        self.app.push_screen(
            ModalInput("passphrase to lock this backup with (you'll need it to restore)", "Backup pair", password=True),
            self._pack_with_passphrase,
        )

    def _pack_with_passphrase(self, pw):
        if not pw:
            return
        try:
            s = encode_mod.pack_tickets(self._pack_appid, pw)
        except ValueError as e:
            self.set_out(f"[red]{e}[/red]")
            return
        ok = clipboard.copy(s)
        self.app.push_screen(ModalInfo(s, title=f"{self._pack_appid}: your backup string (passphrase-locked)"))
        self.set_out(
            f"{'copied' if ok else 'copy failed'} paw1e string for {self._pack_appid} ({len(s)} chars) - keep the passphrase"
        )

    def _restore_tickets(self, text):
        if not text:
            return
        self._restore_data = text.strip()
        self.app.push_screen(
            ModalInput("passphrase for this backup", "Restore pair", password=True), self._restore_with_passphrase
        )

    def _restore_with_passphrase(self, pw):
        if not pw:
            return
        try:
            saved = encode_mod.restore(self._restore_data, pw)
        except ValueError as e:
            self.set_out(f"[red]{e}[/red]")
            return
        self.set_out("restored " + ", ".join(t.filename for t in saved))
        self._draw_tickets(keep_message=True)

    def _detail_selected(self):
        tk = self._selected()
        if tk is None:
            return
        try:
            text = encode_mod.detail_text(tk.appid)
        except ValueError as e:
            self.set_out(f"[red]{e}[/red]")
            return
        self.app.push_screen(ModalInfo(text, title=f"{tk.appid}: both tickets (yours)"))

    def _delete_selected(self):
        tk = self._selected()
        if tk is None:
            return
        self.app.push_screen(
            Confirm(f"Delete {tk.filename} from the cache?\n(a backup copy is kept)", dangerous=True),
            lambda yes, tk=tk: self._do_delete(tk) if yes else None,
        )

    def _do_delete(self, tk):
        from ...util.backup import backup_file

        try:
            if tk.path is not None:
                backup_file(tk.path)
            tickets.delete_ticket(tk)
        except OSError as e:
            self.set_out(f"[red]couldn't delete: {e}[/red]")
            return
        self._draw_tickets(keep_message=True)
        self.set_out(f"deleted {tk.filename}")

    def action_pop(self):
        self.app.pop_screen()
