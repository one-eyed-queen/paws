from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ... import art
from ... import settings
from ... import sls as sls_module
from ...features import FEATURES as _FEATURES
from ...sls.find import find_sls
from ...steam.find import find_steam
from ..widgets.art_panel import AsciiPanel
from ..widgets.backdrop import panel_backdrop
from ..widgets.footer import FooterHelp
from ..widgets.gradient import gradient_text
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar
from ..widgets.menu import Menu, MenuItem, restore_index


DETAIL_KEYS = "\n".join(
    [
        "[#4066ff]" + "─" * 30 + "[/]",
        "[#9db0e0]shortcuts[/]",
        "[#dbe4ff]↑ ↓[/]  [#9db0e0]move[/]      [#dbe4ff]enter[/]  [#9db0e0]run[/]",
        "[#dbe4ff]q  esc[/]  [#9db0e0]quit[/]",
        "",
        "[#9db0e0]drop on the window[/]",
        "[#dbe4ff].manifest .lua .key[/]  [#9db0e0]add a game[/]",
        "[#dbe4ff]dlc page text[/]  [#9db0e0]bulk add[/]",
    ]
)


class MenuPanel(Container):
    DETAIL_MIN = 86
    HINTS_MIN = 62

    def on_mount(self):
        self.backdrop = panel_backdrop(self)

    def on_resize(self, event):
        self.query_one("#menu-detail").display = self.size.width >= self.DETAIL_MIN and not settings.is_minimal()
        compact = self.size.width < self.HINTS_MIN
        if compact != self.has_class("-compact"):
            self.set_class(compact, "-compact")
            for row in self.query(MenuItem):
                row.refresh(layout=False)


class HomeScreen(Screen):
    no_screen_picture = True

    BINDINGS = [("q", "quit_app", "quit"), ("escape", "quit_app", "quit")]

    def compose(self) -> ComposeResult:
        with Horizontal(id="home-body"):
            with Container(id="art-zone"):
                yield AsciiPanel(id="art-home")
            with Vertical(id="right-col"):
                yield AppHeader(id="hdr")
                with MenuPanel(id="menu-panel"):
                    yield Static(gradient_text("MENU " + "·" * 12 + " arrows + enter"), id="menu-panel-title")
                    with Horizontal(id="menu-body"):
                        yield Menu(id="menu", classes="in-panel")
                        with Vertical(id="menu-detail"):
                            yield Static("", id="detail-top", markup=True)
                            yield Static(DETAIL_KEYS, id="detail-keys", markup=True)
                yield Static("", id="home-status")
                yield JobBar(id="job", classes="thin")
                yield FooterHelp("pick something (up/down, enter, q to quit)")

    HOME_MENU = tuple((f.key, f.label, f.desc, f.icon) for f in _FEATURES) + (("quit", "Quit", "Exit paws", "quit"),)

    def on_mount(self):
        self._last_art = None
        self._status_text: list[str] = []
        self.refresh_status()
        self._build_menu()
        self._picked_on_mount = True
        self._refresh_art()

    def on_screen_resume(self, event):
        self._build_menu()
        if getattr(self, "_picked_on_mount", False):
            self._picked_on_mount = False
            return
        self._refresh_art()

    def _refresh_art(self):
        if settings.is_minimal():
            self.query_one("#art-zone").display = False
            return
        if settings.get_setting("random_banner"):
            self._pick_art()
        else:
            self._show_art(art.banner_name())

    @work(thread=True, exclusive=True, group="home-art")
    def _pick_art(self):
        name = art.random_pick() or "placeholder.txt"
        self.app.call_from_thread(self._show_art, name)

    def _show_art(self, name):
        if not self.is_attached:
            return
        self._last_art = name
        panels = self.query("#art-home")
        if not panels or settings.is_minimal():
            return
        panel = panels.first(AsciiPanel)
        self._size_home()
        panel.show(name)
        self._render_status()

    HINTS = {f.key: f.hint for f in _FEATURES} | {"quit": "esc or q"}

    ART_W = 48
    MENU_MIN = 56
    ART_MIN = 20

    def _size_home(self):
        if settings.is_minimal():
            return
        zone = self.query_one("#art-zone")
        total = self.size.width or self.app.size.width
        if not total:
            return
        art_width = min(self.ART_W, total - self.MENU_MIN)
        if art_width < self.ART_MIN:
            zone.display = False
        else:
            zone.display = True
            zone.styles.width = art_width

    def on_resize(self, event):
        self._size_home()

    def _render_detail(self, item=None):
        if item is not None:
            self._detail_item = item
        item = getattr(self, "_detail_item", None)
        if item is None:
            return
        hint = "[#9db0e0]disabled: turn it on in Settings[/]" if item.disabled else "[#9db0e0]enter runs it[/]"
        text = f"[b #ffffff]{item.title}[/]\n\n[#dbe4ff]{item.desc}[/]\n\n{hint}"
        if text != getattr(self, "_detail_text", None):
            self._detail_text = text
            self.query_one("#detail-top", Static).update(text, layout=False)

    def _render_status(self):
        parts = list(getattr(self, "_status_text", []))
        # the release line is drawn from the live value, never baked into a status build: a slow build that
        # started while it was still "checking…" used to land last and leave it stuck on that
        if getattr(self, "_show_latest", True):
            parts.insert(min(2, len(parts)), f"[#9db0e0]latest release: {getattr(self, '_latest', 'checking…')}[/]")
        if getattr(self, "_last_art", None):
            parts.append(f"[#9db0e0]banner: {self._last_art}[/]")
        parts.append(
            "[#9db0e0]⚖ Source-available © 2026 ken (kaneki ken) / Anteiku - no resale, no rebrand, no AI training[/]"
        )
        self.query_one("#home-status", Static).update("\n".join(parts))

    def _shown_entries(self):
        return [e for e in self.HOME_MENU if e[0] in ("settings", "quit") or not settings.is_disabled(e[0])]

    def _build_menu(self):
        menu = self.query_one("#menu", Menu)
        entries = self._shown_entries()
        signature = tuple(key for key, *_ in entries)
        if signature == getattr(self, "_menu_signature", None) and menu.children:
            menu.focus()
            return
        self._menu_signature = signature
        current_index = menu.index
        menu.remove_children()
        n = len(entries)
        menu.extend(
            [
                MenuItem(key, label, desc, icon, hue=i / max(n - 1, 1), hint=self.HINTS.get(key, ""))
                for i, (key, label, desc, icon) in enumerate(entries)
            ]
        )
        if menu.children:
            menu.call_after_refresh(lambda: restore_index(menu, current_index))
        menu.focus()

    @on(Menu.Highlighted)
    def _help(self, event):
        if event.item:
            self._render_detail(event.item)
            self.query_one(FooterHelp).set_desc(event.item.desc)

    @on(Menu.Selected)
    def _pick(self, event):
        item = event.item
        if item is None:
            return
        if item.disabled or settings.is_disabled(item.data):
            self.query_one(FooterHelp).set_desc(item.desc, "disabled - enable it in Settings")
            return
        self.navigate(item.data)

    def navigate(self, key: str | None):
        if key is None:
            return
        if key in settings.FEATURES and settings.is_disabled(key):
            self.query_one(FooterHelp).set_desc("", "disabled - enable it in Settings")
            return
        if key == "quit":
            self.app.exit()
            return
        feature = next((f for f in _FEATURES if f.key == key), None)
        if feature is not None:
            import importlib

            module = importlib.import_module(f"paws.tui.{feature.module}")
            self.app.push_screen(getattr(module, feature.cls)())

    def refresh_status(self):
        self._latest = "checking…"
        self._status_text = []
        self._render_status()
        self._build_status()
        self._load_latest()

    @work(thread=True, exclusive=True)
    def _load_latest(self):
        latest = sls_module.fetch_latest_github_tag() or "?"
        self.app.call_from_thread(self._got_latest, latest)

    def _got_latest(self, latest):
        self._latest = latest
        self._render_status()
        self._announce_update(latest)

    @staticmethod
    def _repair_hint():
        try:
            from ... import repair

            problems = [p for p in repair.scan() if p.id != "config.missing"]
        except Exception:
            return []
        if not problems:
            return []
        colour = "red" if any(p.severity == "error" for p in problems) else "yellow"
        return [f"[{colour}]{len(problems)} thing(s) to repair: Status / Doctor > Repair[/{colour}]"]

    @staticmethod
    def _schema_hint(sls):
        try:
            from ...config import upstream

            github_keys = upstream.fetch_github_keys()
            added, removed = upstream.diff(github_keys) if github_keys is not None else ([], [])
            if not added and not removed:
                installed_keys = upstream.installed_template_keys(sls.lib_dir if sls else None)
                if installed_keys is not None:
                    added, removed = upstream.diff(installed_keys)
        except Exception:
            return []
        if not added and not removed:
            return []
        return ["[yellow]SLSsteam's config keys moved: Status / Doctor for details[/yellow]"]

    def _announce_update(self, latest):
        app = self.app
        if getattr(app, "_update_told", False) or latest in ("?", ""):
            return
        try:
            sls = find_sls()
            if sls and sls_module.update_available(sls, latest):
                app._update_told = True
                app.tell("SLSsteam update available", f"{latest} is out (you have {sls_module.installed_version(sls)})")
        except Exception:
            pass

    _status_gen = 0

    def _build_status(self):
        self._status_gen += 1
        self._build_status_worker(self._status_gen)

    @work(thread=True, exclusive=True, group="home-status")
    def _build_status_worker(self, gen):
        st, sls = find_steam(), find_sls()
        version = sls_module.installed_version(sls) if sls else None
        steam_text = f"Steam: {st.kind} v{st.client_version}" if st else "Steam: not found"
        sls_text = f"SLS: ver={version}" if sls else "SLS: not installed"
        text = [f"[b]{steam_text}[/b]", f"[b]{sls_text}[/b]"]
        self._show_latest = not (sls and sls.kind == "windows")  # the release feed is the linux build
        if sls and not sls.desktop_used and sls.kind != "windows":  # windows has no LD_AUDIT, the dll loads itself
            text.append("[red]LD_AUDIT not wired into the .desktop file[/red]")
        text += self._repair_hint()
        text += self._schema_hint(sls)
        self.app.call_from_thread(self._set_status, text, gen)

    def _set_status(self, text, gen=None):
        if gen is not None and gen != self._status_gen:
            return  # an older build finishing late, a newer one is on its way
        self._status_text = text
        self._render_status()

    def action_quit_app(self):
        self.app.exit()
