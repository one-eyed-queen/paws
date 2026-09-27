from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button, Static

from ... import sls as sls_module
from ...sls.find import find_sls
from ...steam.find import find_steam
from ...util import pkgmgr
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar
from ..widgets.modals import Confirm


class SlsScreen(Screen):
    DEFAULT_CLASSES = "page"
    AUTO_FOCUS = ""

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Install / Update SLSsteam", id="hdr")
        yield Static("", id="sls-status")
        with Grid(id="sls-buttons"):
            yield Button("Install SLSsteam", id="b-install", variant="primary")
            yield Button("Uninstall SLSsteam", id="b-uninstall", variant="error")
            yield Button("Install HeadCrab", id="b-hc-install", variant="primary")
            yield Button("Uninstall HeadCrab", id="b-hc-uninstall", variant="error")
        yield JobBar(id="job")
        yield Static(
            "[#9db0e0]any other build (a .zip or .7z, or a repo link): drop it on this window, paws asks first[/]",
            id="sls-out",
            classes="panel",
        )

    @on(Button.Pressed)
    def _act(self, ev):
        sid = ev.button.id
        if sid == "b-install":
            self._run(
                lambda progress: sls_module.install_release(sls_module.SlsSource("github", "github"), progress=progress)
            )
        elif sid == "b-hc-install":
            self.app.push_screen(
                Confirm(
                    f"Download HeadCrab's installer from\n{sls_module.headcrab.SCRIPT_URL}\nand run it here?\n"
                    "It installs SLSsteam and changes how steam starts. It runs in this terminal, you can watch it "
                    "and answer what it asks.",
                    "Install HeadCrab",
                ),
                self._do_headcrab_install,
            )
        elif sid == "b-hc-uninstall":
            found = sls_module.headcrab.footprint()
            if not found:
                self.set_out("HeadCrab isn't installed (nothing of it found)")
                return
            listing = "\n".join(f"  {p}" for p in found)
            self.app.push_screen(
                Confirm(
                    f"Remove what HeadCrab added?\n{listing}\n(SLSsteam stays, it has its own button)", dangerous=True
                ),
                self._do_headcrab_uninstall,
            )
        elif sid == "b-uninstall":
            sls = find_sls()
            if sls and sls.managed_by:
                self.set_out(
                    f"SLSsteam is owned by {sls.managed_by} ({sls.lib_dir}). "
                    f"paws won't touch package files: remove it with {pkgmgr.remove_hint('slssteam', sls.managed_by)}."
                )
            elif sls:
                self.app.push_screen(
                    Confirm(f"Remove {sls.lib_dir} and the LD_AUDIT .desktop?", dangerous=True), self._do_uninstall
                )
            else:
                self.set_out("nothing to uninstall")

    def _do_headcrab_install(self, yes):
        if yes:
            self.app.run_job(
                "downloading headcrab", lambda progress: sls_module.headcrab.fetch_script(), self._headcrab_fetched
            )

    def _headcrab_fetched(self, result):
        if isinstance(result, Exception):
            self.app.tell("HeadCrab", str(result), "error")
            return
        script, digest = result
        under = getattr(self.app, "underlay", None)
        if under is not None:
            under.pause()
        try:
            with self.app.suspend():
                print(f"running {script} (sha256 {digest}...)\n")
                code = sls_module.headcrab.run_script(script)
                input("\nheadcrab is done. press enter to go back to paws ")
        except sls_module.SlsError as error:
            self.app.tell("HeadCrab", str(error), "error")
            return
        finally:
            if under is not None:
                under.resume()
            self.app.force_full_repaint()
        ok = code == 0
        self.app.tell("HeadCrab", "finished" if ok else f"exited with code {code}", "information" if ok else "error")
        self._say("headcrab finished" if ok else f"[red]headcrab exited with code {code}[/red]")

    def _do_headcrab_uninstall(self, yes):
        if yes:
            self.app.run_job(
                "removing headcrab", lambda progress: sls_module.headcrab.uninstall(progress), self._headcrab_removed
            )

    def _headcrab_removed(self, result):
        if isinstance(result, Exception):
            self.app.tell("HeadCrab", f"couldn't remove it: {result}", "error")
            self._say(f"[red]failed:[/red] {result}")
            return
        self.app.tell("HeadCrab removed", f"{len(result)} item(s)")
        self._say(f"removed {len(result)} thing(s) HeadCrab added")

    def _do_uninstall(self, yes):
        if yes:
            self.app.run_job("uninstalling", lambda progress: sls_module.uninstall(find_sls()), self._uninstalled)

    def _uninstalled(self, result):
        if isinstance(result, Exception):
            self.app.tell("SLSsteam", str(result), "error")
            self._say(f"[red]failed:[/red] {result}")
            return
        self.app.tell("SLSsteam removed")
        self._say("uninstalled")

    def _run(self, action):
        self.set_out("")
        self.app.run_job("installing", lambda progress: action(lambda f: progress(f, "downloading")), self._installed)

    def _installed(self, result):
        if isinstance(result, Exception):
            self.app.tell("SLSsteam install failed", str(result)[:200], "error")
            self._say(f"[red]failed:[/red] {result}")
            return
        self.app.tell("SLSsteam installed", "install / update finished")
        self._say(f"done -> so={result.sls_so if result else None}")

    def _say(self, text):
        # the screen may be gone by the time a job ends: the job doesn't care, only the message would
        if self.is_attached:
            self.set_out(text)
            self.on_status()

    def on_status(self):
        self._load_status()

    @work(thread=True, exclusive=True, group="sls-status")
    def _load_status(self):
        sls, st = find_sls(), find_steam()
        version = sls_module.installed_version(sls) if sls else None
        latest = sls_module.fetch_latest_github_tag() or "?"
        text = f"steam={st.client_version if st else '?'}  sls={version or 'none'}  latest={latest}"
        self.app.call_from_thread(self.query_one("#sls-status", Static).update, text)

    def on_mount(self):
        self.on_status()

    def set_out(self, text: str):
        self.query_one("#sls-out", Static).update(text)

    def action_pop(self):
        self.app.pop_screen()
