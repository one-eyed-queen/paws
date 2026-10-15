"""one place that answers: what am I running on, where is steam, what is it running, and what is
driving it.

everything here is assembled from the helpers that already do the real work (util.distro,
steam.find, sls.find, sls.version, windows.port, sls.headcrab) rather than repeating them, so
there is a single answer to each question and the doctor, the home screen and `paws info` can all
read the same snapshot instead of each poking around on their own.

the shape is deliberately the same on both systems. on linux the backend is SLSsteam or
HeadCrab; on windows it is OpenValve or HubCapTools. both collapse into `Backend.kind`, so
callers never need to branch on the OS to find out what's in charge.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path

from .util import pkgmgr


@dataclass
class Os:
    """the machine, not the install. `id` is the thing worth branching on (`windows`, `arch`,
    `ubuntu`), `family` is the broader group (`debian`, `rhel`, ...)"""

    id: str = "unknown"
    name: str = "Linux"
    family: str = "other"
    release: str = ""
    arch: str = ""
    immutable: bool = False
    immutable_note: str = ""
    package_managers: list[str] = field(default_factory=list)

    def line(self) -> str:
        base = f"{self.name} {self.release}".strip()
        return " ".join(x for x in (base, f"({self.arch})" if self.arch else "", f"[{self.id}/{self.family}]") if x)


@dataclass
class Steam:
    """steam itself. `found` is False rather than None so a missing steam never explodes a caller"""

    found: bool = False
    root: str = ""
    binary: str = ""
    client_version: str = ""
    channel: str = ""
    package: str = ""
    running: bool = False
    sls_injected: bool = False
    hint: str = ""

    def line(self) -> str:
        if not self.found:
            return f"not found{' - ' + self.hint if self.hint else ''}"
        bits = [f"client {self.client_version or '?'}", f"{self.channel}"]
        if self.package:
            bits.append(f"via {self.package}")
        if self.root:
            bits.append(self.root)
        return "  ".join(b for b in bits if b)


@dataclass
class Backend:
    """whatever is actually driving steam's depot access.

    kind is "slssteam", "headcrab", "openvalve", "hubcaptools" or "" when nothing is found.
    `version` is what paws can honestly report - never a guess.
    """

    kind: str = ""
    detail: str = ""
    version: str = ""
    latest: str = ""
    managed_by: str = ""
    config: str = ""
    cache: str = ""
    injected: bool = False
    update_state: str = ""
    update_why: str = ""
    installable: bool = False
    note: str = ""

    def line(self) -> str:
        if not self.kind:
            return self.note or "nothing found"
        # a package-managed version reads "slssteam 20260820085507-1 (pacman)" and already names
        # itself, so only prefix the kind when it isn't there yet
        head = self.version if self.version.startswith(self.kind) else f"{self.kind} {self.version}".strip()
        return f"{head}  {self.detail}" if self.detail else head


@dataclass
class Snapshot:
    os: Os = field(default_factory=Os)
    steam: Steam = field(default_factory=Steam)
    backend: Backend = field(default_factory=Backend)
    paws_version: str = ""

    def as_dict(self) -> dict:
        """plain data, for --json and for anything that wants to serialise it"""
        return {
            "paws": self.paws_version,
            "os": {
                "id": self.os.id,
                "name": self.os.name,
                "family": self.os.family,
                "release": self.os.release,
                "arch": self.os.arch,
                "immutable": self.os.immutable,
                "package_managers": self.os.package_managers,
            },
            "steam": {
                "found": self.steam.found,
                "root": self.steam.root,
                "binary": self.steam.binary,
                "client_version": self.steam.client_version,
                "channel": self.steam.channel,
                "package": self.steam.package,
                "running": self.steam.running,
                "sls_injected": self.steam.sls_injected,
            },
            "backend": {
                "kind": self.backend.kind,
                "version": self.backend.version,
                "latest": self.backend.latest,
                "managed_by": self.backend.managed_by,
                "config": self.backend.config,
                "cache": self.backend.cache,
                "injected": self.backend.injected,
                "update_state": self.backend.update_state,
                "update_why": self.backend.update_why,
                "detail": self.backend.detail,
            },
        }

    def report(self) -> str:
        lines = [
            f"paws       {self.paws_version}",
            f"os         {self.os.line()}",
            f"steam      {self.steam.line()}",
            f"backend    {self.backend.line()}",
        ]
        if self.backend.update_why:
            lines.append(f"updates    {self.backend.update_why}")
        if self.backend.note:
            lines.append(f"note       {self.backend.note}")
        return "\n".join(lines)


def detect_os() -> Os:
    from .windows import IS_WINDOWS

    managers = pkgmgr.available()
    if IS_WINDOWS:
        return Os(
            id="windows",
            name=f"Windows {platform.release()}",
            family="windows",
            release=platform.version(),
            arch=platform.machine(),
            package_managers=managers,
        )
    from .util import distro

    d = distro.detect()
    return Os(
        id=d.id,
        name=f"{d.name} {d.variant_id}".strip() or "Linux",
        family=d.family,
        release=platform.release(),
        arch=platform.machine(),
        immutable=d.immutable,
        immutable_note=d.immutable_note,
        package_managers=managers,
    )


def detect_steam() -> Steam:
    from . import steam as steam_mod
    from .steam.find import find_steam

    st = find_steam()
    if st is None:
        hints = pkgmgr.install_hints("steam")
        return Steam(found=False, hint="  |  ".join(hints) if hints else "install steam with your package manager")
    running, injected = False, False
    try:
        running = steam_mod.is_running()
        injected = bool(running and steam_mod.sls_injected())
    except Exception:
        # asking a steam that isn't there can fail in platform specific ways; detection must not
        # be the thing that breaks
        pass
    return Steam(
        found=True,
        root=str(st.root or ""),
        binary=str(st.binary or ""),
        client_version=st.client_version or "",
        channel=st.channel or "",
        package=st.package or "",
        running=running,
        sls_injected=injected,
    )


# the whole family, in one place. all four are the same idea - an SLSsteam-based build that talks to
# steam - and they differ by who made them and whether the source is open. two are linux, two are
# windows. paws doesn't care which one is "the" one, it just reports what's actually on the machine
BACKENDS = {
    "slssteam": {"os": "linux", "title": "SLSsteam", "open": True},
    "headcrab": {"os": "linux", "title": "HeadCrab", "open": False},
    "hubcaptools": {"os": "windows", "title": "HubCapTools", "open": False},
    "openvalve": {"os": "windows", "title": "OpenValve", "open": False},
}


def backends_for(is_windows: bool) -> tuple[str, ...]:
    """the builds that can run on this system"""
    want = "windows" if is_windows else "linux"
    return tuple(k for k, v in BACKENDS.items() if v["os"] == want)


def describe(kind: str) -> str:
    """'HubCapTools (SLSsteam build, closed source)' - for places that need to say what a name means"""
    meta = BACKENDS.get(kind)
    if not meta:
        return kind
    if kind == "slssteam":  # the one everything else is built on, so it needs no "build" label
        return "SLSsteam (open source, the one the others are built on)"
    source = "open source" if meta["open"] else "closed source"
    return f"{meta['title']} (SLSsteam build, {source})"


def detect_backend() -> Backend:
    """what's driving steam. linux has SLSsteam and HeadCrab, windows has OpenValve and HubCapTools -
    all SLSsteam builds, all found by looking rather than by assuming"""
    from .windows import IS_WINDOWS

    return _windows_backend() if IS_WINDOWS else _linux_backend()


def _linux_backend() -> Backend:
    """SLSsteam and HeadCrab are independent here: HeadCrab is its own build, not a wrapper around
    SLSsteam, so both are looked for and both get reported if both are present"""
    from .sls import headcrab
    from .sls.find import find_sls
    from .sls.version import fetch_latest_github_tag, installed_version, update_reason, update_state

    footprint = headcrab.footprint()
    sls = find_sls()

    if sls is None:
        if footprint:
            return Backend(
                kind="headcrab",
                detail=f"{len(footprint)} thing(s) it put on this machine",
                injected=True,
                installable=False,
                note="HeadCrab is an SLSsteam build, so its config is the standard one - everything in "
                "Add game and drop works on it as is",
            )
        return Backend(
            installable=True,
            note="nothing installed yet - Install SLSsteam, drop a build (.zip/.7z/.tar) on the window, "
            "or install HeadCrab's own installer",
        )

    latest = fetch_latest_github_tag()
    also = ""
    if footprint:
        also = f"  (+ HeadCrab, {len(footprint)} thing(s) of it here)"
    return Backend(
        kind="slssteam",
        detail=(f"lib={sls.sls_so.name}" if sls.sls_so else "") + also,
        version=installed_version(sls) or "",
        latest=latest or "",
        managed_by=sls.managed_by or "",
        config=str(sls.config or ""),
        cache=str(sls.cache or ""),
        injected=bool(sls.lib_dir and sls.lib_dir.exists()),
        update_state=update_state(sls, latest),
        update_why=update_reason(sls, latest),
    )


def _windows_backend() -> Backend:
    """OpenValve is a manager with nothing to install; HubCapTools is a dll proxy paws can fetch.
    both are found the same way - by where their config lives - so this never has to guess"""
    from .windows import port

    which = port.detect()
    if which == "openvalve":
        cfg = port.openvalve_config()
        return Backend(
            kind="openvalve",
            detail=f"config={cfg}",
            config=str(cfg),
            cache=str(cfg.parent / "cache"),
            injected=cfg.exists(),
            installable=False,
            note="OpenValve is an SLSsteam build, so its config is the standard one - paws reads and "
            "writes it directly, there's nothing to install or update",
        )
    if which == "hubcaptools":
        dll = port.proxy_dll()
        return Backend(
            kind="hubcaptools",
            detail=f"proxy={dll.name if dll else ''}",
            version=port.installed_version() or "",
            latest=port.latest_version() or "",
            config=str(port.config_dir() or ""),
            cache=str((port.config_dir() or Path(".")) / "cache"),
            injected=True,
            installable=True,
            note="close steam before installing or updating - the proxy dll goes next to steam.exe",
        )
    return Backend(
        installable=True,
        note="nothing found - Install fetches HubCapTools from its repo, or use OpenValve's own installer",
    )


def snapshot() -> Snapshot:
    """everything at once, for `paws info`, the home screen and the doctor"""
    from . import __version__

    return Snapshot(os=detect_os(), steam=detect_steam(), backend=detect_backend(), paws_version=__version__)
