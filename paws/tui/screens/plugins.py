from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from ... import editor
from ...paths import HOME
from ...sls import SlsError, plugins
from ..widgets.header import AppHeader
from ..widgets.modals import Confirm, ModalInput


class PluginsScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back"), ("e", "edit", "edit")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Plugins / Add-ons", id="hdr")
        yield Static("", id="plug-status")
        yield DataTable(id="plug-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="plug-out", classes="panel")
        with Horizontal(id="plug-buttons"):
            yield Button("New", variant="primary", id="b-new")
            yield Button("Import", id="b-import")
            yield Button("Export", id="b-export")
            yield Button("Enable/Disable", id="b-toggle")
            yield Button("Edit", id="b-edit")
            yield Button("Remove", variant="error", id="b-remove")
            yield Button("Master switch", id="b-master")
            yield Button("Back", id="b-back")

    def on_mount(self):
        t = self.query_one("#plug-table", DataTable)
        t.add_columns("plugin", "state", "version", "author")
        self.refresh_list()

    def refresh_list(self, message: str = ""):
        self.plugins = plugins.list_plugins()
        t = self.query_one("#plug-table", DataTable)
        keep = t.cursor_row
        t.clear()
        for p in self.plugins:
            t.add_row(p.title, "on" if p.enabled else "off", p.version, p.author, key=p.name)
        if self.plugins:
            t.focus()
            t.move_cursor(row=min(keep, len(self.plugins) - 1))
            self._describe(t.cursor_row)
        else:
            self.set_out(
                (message + "\n" if message else "")
                + "[#9db0e0]no plugins yet: New writes one from a template, Import brings in a .lua or a "
                "shared .paws-plugin.zip[/]"
            )
        master = plugins.master_on()
        self.query_one("#plug-status", Static).update(
            f"Plugins config key: [{'#3ddc97' if master else '#ff5c7a'}]{'on' if master else 'off'}[/] "
            "(off means none of them run, even the ones listed as on below)"
        )

    def set_out(self, text: str):
        self.query_one("#plug-out", Static).update(text)

    def _describe(self, row: int):
        p = self._at(row)
        if p is None:
            return
        self.set_out(f"[b]{p.title}[/b]  [#9db0e0]{p.version}[/]  {p.author}\n{p.desc}\n[#9db0e0]{p.path}[/]")

    def _at(self, row: int):
        return self.plugins[row] if self.plugins and 0 <= row < len(self.plugins) else None

    def selected(self):
        t = self.query_one("#plug-table", DataTable)
        return self._at(t.cursor_row) if self.plugins else None

    @on(DataTable.RowHighlighted)
    def _hi(self, ev):
        self._describe(ev.cursor_row)

    @on(Button.Pressed, "#b-new")
    def _new(self):
        self.app.push_screen(
            ModalInput("Name for the new plugin (a-z, digits, spaces, - and _)", "New plugin"), self._made
        )

    def _made(self, name: str | None):
        if not name or not name.strip():
            return
        try:
            plugin = plugins.new_plugin(name.strip())
        except SlsError as error:
            self.set_out(f"[red]{error}[/red]")
            return
        self.refresh_list(f"wrote {plugin.path.name}")
        self._open_in_editor(plugin.path)

    @on(Button.Pressed, "#b-edit")
    def _edit(self):
        self.action_edit()

    def action_edit(self):
        p = self.selected()
        if p is None:
            self.set_out("[yellow]pick a plugin in the list first[/yellow]")
            return
        self._open_in_editor(p.path)

    def _open_in_editor(self, path):
        under = getattr(self.app, "underlay", None)
        if under is not None:
            under.pause()
        try:
            result = editor.open_in_editor(path, suspend=self.app.suspend)
        finally:
            if under is not None:
                under.resume()
            self.app.force_full_repaint()
        if not result.ran:
            self.set_out(f"[red]{result.error}[/red]")
            return
        self.refresh_list(f"saved in {result.editor}" if result.changed else "nothing changed")

    @on(Button.Pressed, "#b-import")
    def _import(self):
        self.app.push_screen(
            ModalInput(
                "Path to a .lua file or a .paws-plugin.zip (drag & drop onto this terminal works too)", "Import"
            ),
            self._do_import,
        )

    def _do_import(self, path: str | None):
        if not path or not path.strip():
            return
        try:
            got = plugins.import_plugin(path.strip().strip("'\""))
        except SlsError as error:
            self.set_out(f"[red]{error}[/red]")
            return
        self.refresh_list(f"imported {got.name} (off, enable it when you're ready)")

    @on(Button.Pressed, "#b-export")
    def _export(self):
        p = self.selected()
        if p is None:
            self.set_out("[yellow]pick a plugin in the list first[/yellow]")
            return
        self.app.push_screen(
            ModalInput("Folder to write the .paws-plugin.zip into", "Export", default=str(HOME)),
            lambda folder, p=p: self._do_export(p, folder),
        )

    def _do_export(self, p, folder: str | None):
        if not folder or not folder.strip():
            return
        try:
            written = plugins.export_plugin(p.name, folder.strip())
        except SlsError as error:
            self.set_out(f"[red]{error}[/red]")
            return
        self.set_out(f"[green]wrote {written}[/green]")

    @on(Button.Pressed, "#b-toggle")
    def _toggle(self):
        p = self.selected()
        if p is None:
            self.set_out("[yellow]pick a plugin in the list first[/yellow]")
            return
        try:
            changed = plugins.disable(p.name) if p.enabled else plugins.enable(p.name)
        except SlsError as error:
            self.set_out(f"[red]{error}[/red]")
            return
        self.refresh_list(f"{changed.name}: {'on' if changed.enabled else 'off'}")

    @on(Button.Pressed, "#b-remove")
    def _remove(self):
        p = self.selected()
        if p is None:
            self.set_out("[yellow]pick a plugin in the list first[/yellow]")
            return
        self.app.push_screen(
            Confirm(f"Remove {p.title}?\n(a copy is kept in the backups)", dangerous=True),
            lambda yes, p=p: self._do_remove(p) if yes else None,
        )

    def _do_remove(self, p):
        try:
            message = plugins.remove(p.name)
        except SlsError as error:
            self.set_out(f"[red]{error}[/red]")
            return
        self.refresh_list(message)

    @on(Button.Pressed, "#b-master")
    def _master(self):
        plugins.set_master(not plugins.master_on())
        self.refresh_list()

    @on(Button.Pressed, "#b-back")
    def _back(self):
        self.action_pop()

    def action_pop(self):
        self.app.pop_screen()
