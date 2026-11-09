from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Static

from ...steam import tinker
from ..widgets.header import AppHeader
from ..widgets.modals import Confirm, ModalInput, ModalPick

GOOD, BAD, WARN, DIM = "#3ddc97", "#ff5c7a", "#ffd75f", "#9db0e0"


class TinkerScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back"), ("r", "reload", "refresh")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Steam Tinker", id="hdr")
        yield Static("", id="tink-status")
        yield Static("", id="tink-out", classes="panel")
        with Horizontal(id="tink-buttons"):
            yield Button("32 / 64 bit", variant="primary", id="b-arch")
            yield Button("Channel (stable / beta)", id="b-channel")
            yield Button("Hold updates", id="b-hold")
            yield Button("Roll back (downgrade)", id="b-rollback")
            yield Button("Update to newest", id="b-upgrade")
            yield Button("Back", id="b-back")

    def on_mount(self):
        self.state = None
        self.reload()
        self.query_one("#b-arch", Button).focus()

    def set_out(self, text: str):
        self.query_one("#tink-out", Static).update(text)

    def action_reload(self):
        self.reload()

    def reload(self, message: str = ""):
        try:
            self.state = tinker.state()
        except tinker.TinkerError as error:
            self.state = None
            self.query_one("#tink-status", Static).update(f"[{BAD}]{error}[/]")
            return
        s = self.state
        sls = ""
        if s.sls_fits is True:
            sls = f"[{GOOD}]your SLSsteam is {s.sls_bits}-bit too, it fits[/]"
        elif s.sls_fits is False:
            sls = (
                f"[{BAD}]your SLSsteam is {s.sls_bits}-bit: steam drops it. switch the client to {s.sls_bits}-bit "
                f"or install a {s.bits}-bit SLSsteam[/]"
            )
        arch = f"{s.bits}-bit" + ("" if s.can_64 else f" [{DIM}](no 64-bit client in this steam yet)[/]")
        forced = f"\n[{WARN}]STEAM_FORCE_CLIENT={s.forced} is set and decides the bitness[/]" if s.forced else ""
        self.query_one("#tink-status", Static).update(
            f"client [b]{s.version or '?'}[/b] · [b]{arch}[/b] · channel [b]{s.channel_label}[/b] · updates "
            + (f"[{WARN}]held[/]" if s.held else f"[{GOOD}]on[/]")
            + (f" · [{WARN}]steam is running, close it to change anything[/]" if s.running else "")
            + (f"\n{sls}" if sls else "")
            + forced
        )
        self.query_one("#b-hold", Button).label = "Let it update" if s.held else "Hold updates"
        self.set_out(
            message
            or f"[{DIM}]32 / 64 bit picks which steam client starts (SLSsteam has to be the same bitness). channel "
            "is stable or a beta. hold stops steam updating itself. roll back puts the 32-bit client on an older "
            "release and holds it there, for when an update broke SLSsteam. all of it applies the next time steam "
            "starts[/]"
        )

    def _done(self, result):
        if isinstance(result, Exception):
            self.reload(f"[{BAD}]{result}[/]")
        else:
            self.reload(f"[{GOOD}]{result}[/]")

    def _try(self, action):
        try:
            self._done(action())
        except tinker.TinkerError as error:
            self._done(error)
        except OSError as error:
            self._done(tinker.TinkerError(f"couldn't write it: {error}"))

    @on(Button.Pressed, "#b-arch")
    def _arch(self):
        s = self.state
        if s is None:
            return
        no64 = None if s.can_64 else "this steam has no 64-bit client yet"
        self.app.push_screen(
            ModalPick(
                "Which steam client starts",
                "the 64-bit one is valve's newer client. SLSsteam must match: a 32-bit build only loads into the "
                "32-bit client and a 64-bit build only into the 64-bit one",
                [
                    (
                        ("● " if s.bits == 32 else "") + "32-bit",
                        "32",
                        None,
                        "ubuntu12_32/steam, what most SLSsteam builds hook",
                    ),
                    (("● " if s.bits == 64 else "") + "64-bit", "64", no64, "steamrt64/steam, needs a 64-bit SLSsteam"),
                ],
            ),
            self._arch_picked,
        )

    def _arch_picked(self, value):
        if value:
            self._try(lambda: tinker.set_bits(None, int(value)))

    @on(Button.Pressed, "#b-channel")
    def _channel(self):
        s = self.state
        if s is None:
            return
        options = [
            (("● " if s.channel == name else "") + label, name or "stable", None, desc)
            for name, label, desc in tinker.BRANCHES
        ]
        options.append(("another branch…", "?", None, "type its name"))
        self.app.push_screen(
            ModalPick("Steam client channel", "steam updates onto it the next time it starts", options),
            self._channel_picked,
        )

    def _channel_picked(self, value):
        if value == "?":
            self.app.push_screen(ModalInput("Branch name, like publicbeta", "Client branch"), self._channel_picked)
            return
        if value and value.strip():
            branch = value.strip()
            self.set_out(f"[{DIM}]checking valve has {branch}…[/]")
            self.app.run_job("steam channel", lambda progress: tinker.set_channel(None, branch), self._done)

    @on(Button.Pressed, "#b-hold")
    def _hold(self):
        s = self.state
        if s is not None:
            self._try(lambda: tinker.set_hold(None, not s.held))

    @on(Button.Pressed, "#b-upgrade")
    def _upgrade(self):
        s = self.state
        if s is None:
            return
        steps = []
        if s.held:
            steps.append("lets steam update again (takes the hold off)")
        if s.channel:
            steps.append(f"keeps you on {s.channel_label}: use Channel for stable")
        self.app.push_screen(
            Confirm(
                "Update steam to the newest client?\n"
                + ("this " + "; ".join(steps) + ". " if steps else "")
                + "steam updates itself the next time it starts.\n"
                "if SLSsteam doesn't support that client yet, roll back again",
                "Update",
            ),
            lambda yes: yes and self._try(lambda: tinker.set_hold(None, False)),
        )

    @on(Button.Pressed, "#b-rollback")
    def _rollback(self):
        s = self.state
        if s is None:
            return
        if s.bits != 32:
            self.set_out(f"[{WARN}]only 32-bit client releases are archived: switch to 32-bit first[/]")
            return
        if s.channel:
            self.set_out(f"[{WARN}]you're on {s.channel_label}: switch the channel to stable first[/]")
            return
        self.set_out(f"[{DIM}]asking the web archive which older releases it kept…[/]")
        self._load_builds()

    @work(thread=True, exclusive=True)
    def _load_builds(self):
        builds = tinker.archived_builds()
        self.app.call_from_thread(self._pick_build, builds)

    def _pick_build(self, builds):
        if not builds:
            self.set_out(f"[{BAD}]the web archive didn't answer, or has no older releases saved. try again later[/]")
            return
        self.builds = {b.stamp: b for b in builds}
        self.app.push_screen(
            ModalPick(
                "Roll steam back to",
                "saved copies of valve's release list, newest first. the files themselves come from valve",
                [(b.date, b.stamp) for b in builds],
            ),
            self._build_picked,
        )

    def _build_picked(self, stamp):
        build = self.builds.get(stamp) if stamp else None
        if build is None:
            return
        self.app.push_screen(
            Confirm(
                f"Roll the steam client back to the release from {build.date}?\n"
                "paws runs steam's own updater with the old release list (steam opens its update window and "
                "closes itself when it's done, a few minutes), then holds updates so it stays there.\n"
                "your games, logins and SLSsteam config aren't touched. Update to newest undoes it",
                "Roll back",
                dangerous=True,
            ),
            lambda yes: yes and self._run_rollback(build),
        )

    def _run_rollback(self, build):
        self.app.run_job("steam rollback", lambda progress: tinker.rollback(None, build, progress), self._rolled)

    def _rolled(self, result):
        if isinstance(result, Exception):
            self.reload(f"[{BAD}]{result}[/]")
            return
        if result["ok"]:
            self.reload(f"[{GOOD}]steam is on {result['after']} now (was {result['before']}), updates held[/]")
        else:
            self.reload(
                f"[{BAD}]steam's updater finished but the client is still {result['after']} (wanted "
                f"{result['target']}). steam may have refused that release, try another date[/]"
            )

    @on(Button.Pressed, "#b-back")
    def _back(self):
        self.action_pop()

    def action_pop(self):
        self.app.pop_screen()
