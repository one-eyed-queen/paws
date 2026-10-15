from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button, Static

from ... import sls as sls_module
from ...sls.find import find_sls
from ...steam.find import find_steam
from ...util import pkgmgr
from ...windows import IS_WINDOWS
from ...windows.port import UNDER_CONSTRUCTION, WORKS_WITHOUT_PORT
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar
from ..widgets.modals import Confirm, ModalPick

WINDOWS_NOTE = "[#9db0e0]" + UNDER_CONSTRUCTION + "[/]"


def _any_source(variant: str = "any", flavour: str = "release"):
    """the github release source. windows ignores variant/flavour and goes to the port's own
    installer instead - there is only one HubCapTools build"""
    return sls_module.SlsSource("github", "github", variant=variant, flavour=flavour)


def _build_options():
    """the four SLSsteam assets, minus whatever this machine can't use.

    the Arch package is a native pacman package, so it only makes sense on arch and family - on
    anything else the portable .7z is the one to take. what the newest release actually publishes
    is asked of github, so a release that only ships one flavour doesn't offer the other.
    """
    from ... import detect

    family = detect.detect_os().family
    arch_ok = family in ("arch", "manjaro", "endeavouros", "cachyos", "garuda", "blackarch")
    try:
        rels = sls_module.github_releases(limit=1, timeout=10)
        available = rels[0].available() if rels else {}
    except Exception:
        available = {}  # offline: offer the full set rather than blocking the install
    options = []
    for variant, label, blurb in (
        ("any", "Any", "portable, works on any distro"),
        ("arch", "Arch", "native pacman package"),
    ):
        for flavour in ("release", "debug"):
            if variant == "arch" and not arch_ok:
                options.append((f"{label} · {flavour}", f"{variant}/{flavour}", f"{family} - not an arch system"))
                continue
            hint = None if flavour == "release" else "unoptimised, with logs"
            if available and flavour not in available.get(variant, ()):
                options.append((f"{label} · {flavour}", f"{variant}/{flavour}", "this release doesn't have one"))
                continue
            options.append(
                (f"{label} · {flavour}", f"{variant}/{flavour}", None, f"{blurb}{', ' + hint if hint else ''}")
            )
    return options


def _install_options():
    """(label, value, note) per product. a note greys the option out and explains why.

    which are live comes from the os detector rather than a hardcoded platform check, so the
    offered list and `paws info` can never disagree about what machine this is.
    """
    from ... import detect

    here = "windows" if detect.detect_os().id == "windows" else "linux"
    options = []
    for label, value, want in _PRODUCTS:
        if value == "openvalve" and here == "windows":
            note = "a manager - nothing for paws to install"
        elif want != here:
            note = f"{want} only"
        else:
            note = None
        options.append((label, value, note))
    return options


# every SLSsteam build paws knows how to put a name to, and the os it runs on. a note greys the
# option out, so the whole family stays visible instead of half of it silently disappearing
_PRODUCTS = (
    ("SLSsteam", "slssteam", "linux"),
    ("HeadCrab", "headcrab", "linux"),
    ("OpenValve", "openvalve", "windows"),
    ("HubCapTools", "hubcaptools", "windows"),
)


class SlsScreen(Screen):
    DEFAULT_CLASSES = "page"
    AUTO_FOCUS = ""

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Install / Update / Uninstall", id="hdr")
        yield Static("", id="sls-status")
        # three buttons, one row. which product to install is a question for the install dialog,
        # not four more buttons crowding this line
        with Grid(id="sls-buttons"):
            yield Button("Install", id="b-install", variant="primary")
            yield Button("Update", id="b-update", variant="primary")
            yield Button("Uninstall", id="b-uninstall", variant="error")
        yield JobBar(id="job")
        yield Static(
            WINDOWS_NOTE
            if IS_WINDOWS
            else "[#9db0e0]any other build (a .zip or .7z, or a repo link): drop it on this window, paws asks first[/]",
            id="sls-out",
            classes="panel",
        )

    @on(Button.Pressed)
    def _act(self, ev):
        sid = ev.button.id
        if sid == "b-install":
            self._ask_product()
        elif sid == "b-update":
            if IS_WINDOWS:
                # windows has no github release to compare against - HubCapTools ships a build in
                # its repo, so "is there an update" is a different question with a different answer
                self._run("updating", lambda progress: sls_module.update_port(progress))
                return
            sls = find_sls()
            if sls is None:
                self.set_out("[#9db0e0]nothing to update yet - use Install SLSsteam[/]")
                return
            latest = sls_module.fetch_latest_github_tag()
            state = sls_module.update_state(sls, latest)
            reason = sls_module.update_reason(sls, latest)
            if state == sls_module.UNKNOWN:
                self.set_out(
                    f"[#9db0e0]can't tell whether there's an update: {reason}. Install will fetch it anyway.[/]"
                )
            elif state == sls_module.NO:
                self.set_out(f"[#9db0e0]already on the newest github build - {reason}[/]")
                return
            self._run(
                "updating",
                lambda progress: sls_module.install_release(
                    sls_module.SlsSource("github", "github"), progress=progress
                ),
            )
        elif sid == "b-uninstall-hc":
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
            if not IS_WINDOWS and sls is None and sls_module.headcrab.footprint():
                # only headcrab is here. offer to take it off rather than saying "nothing to
                # uninstall", which is what it used to do
                self._ask_uninstall_headcrab()
                return
            if sls and sls.kind == "windows":
                # this used to just print a note and return, which read exactly like the button
                # had done its job. say plainly that nothing was removed, and say why
                self.set_out(
                    "[#9db0e0]nothing was removed.[/] removing a windows port isn't implemented yet "
                    "(it depends on how HubCapTools and OpenValve install themselves), so paws won't "
                    "guess at which files are yours to delete. your config.yaml and tickets are untouched.\n\n"
                    f"works on windows anyway: {WORKS_WITHOUT_PORT}"
                )
            elif sls and sls.managed_by:
                # say plainly that nothing was removed, and give the exact line to paste. the
                # old wording read like it had done the job
                self.set_out(
                    f"[#9db0e0]nothing was removed.[/] SLSsteam here belongs to {sls.managed_by} "
                    f"({sls.lib_dir}), and paws never edits files a package manager owns.\n\n"
                    f"  {pkgmgr.remove_hint('slssteam', sls.managed_by)}\n\n"
                    f"run that, then come back - or install SLSsteam into your own home with the "
                    f"Install button, which paws does own and can remove."
                )
            elif sls:
                self.app.push_screen(
                    Confirm(f"Remove {sls.lib_dir} and the LD_AUDIT .desktop?", dangerous=True), self._do_uninstall
                )
            else:
                self.set_out("nothing to uninstall")

    # ---- what are we installing? ------------------------------------------------------------
    # every option is an SLSsteam build, so this is one question with one answer per product.
    # the OS decides which are offered: the linux ones can't run on windows and vice versa, so
    # they're shown greyed out with the reason rather than hidden - you can see the whole family
    # and which half is yours.

    def _ask_product(self):
        self.app.push_screen(
            ModalPick(
                "Install",
                "All of these are SLSsteam builds. pick the one you want.",
                _install_options(),
            ),
            self._product_chosen,
        )

    def _product_chosen(self, choice):
        if not choice:
            return
        if choice == "slssteam":
            self._ask_build()
        elif choice == "headcrab":
            self._confirm_headcrab()
        elif choice == "hubcaptools":
            self._run("installing", lambda progress: sls_module.install_release(_any_source(), progress=progress))
        elif choice == "openvalve":
            self.set_out(
                "[#9db0e0]nothing installed.[/] OpenValve is a manager with no download and no "
                "source, so there is nothing for paws to fetch or unpack - install it with its own "
                "installer, then paws reads and writes %AppData%\\SLSsteam\\config.yaml directly.\n\n"
                f"what works meanwhile: {WORKS_WITHOUT_PORT}"
            )

    def _ask_build(self):
        """SLSsteam publishes four assets: a portable "Any" .7z or a native "Arch" package, each
        in a release or a debug flavour. ask for both, and only offer what this machine can use
        and what the release actually has."""
        self.app.push_screen(
            ModalPick(
                "Install SLSsteam",
                "Which build?",
                _build_options(),
            ),
            self._build_chosen,
        )

    def _build_chosen(self, choice):
        if not choice:
            return
        variant, flavour = choice.split("/")
        self._run(
            f"installing {variant}/{flavour}",
            lambda progress: sls_module.install_release(_any_source(variant, flavour), progress=progress),
        )

    def _confirm_headcrab(self):
        self.app.push_screen(
            Confirm(
                f"Download HeadCrab's installer from\n{sls_module.headcrab.SCRIPT_URL}\nand run it here?\n"
                "It installs HeadCrab (an SLSsteam build) and changes how steam starts. It runs in this terminal, you can watch it "
                "and answer what it asks.",
                "Install HeadCrab",
            ),
            self._do_headcrab_install,
        )

    def _ask_uninstall_headcrab(self):
        self.app.push_screen(
            Confirm(
                "HeadCrab is the only build here. remove what it added?",
                "Uninstall HeadCrab",
                dangerous=True,
            ),
            self._do_headcrab_uninstall,
        )

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

    def _run(self, action, label="installing"):
        self.set_out("")
        self.app.run_job(label, lambda progress: action(lambda f: progress(f, "downloading")), self._installed)

    def _installed(self, result):
        if isinstance(result, Exception):
            self.app.tell("SLSsteam install failed", str(result)[:200], "error")
            self._say(f"[red]failed:[/red] {result}")
            return
        # don't claim success on the strength of "it didn't throw" - an install that wrote no
        # library (a source archive, an empty zip) used to report a cheerful "installed" and
        # change nothing at all
        so = getattr(result, "sls_so", None) if result else None
        if not so or not Path(so).exists():
            self.app.tell(
                "SLSsteam not installed", "nothing was written - that archive has no built library in it", "error"
            )
            self._say(
                "[red]nothing was written. that file has no built library in it - it may be source code, not a release.[/red]"
            )
            return
        self.app.tell("SLSsteam installed", f"{Path(so).name} is in place - restart steam to load it")
        self._say(f"done -> so={so}. restart steam for it to take effect.")

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
