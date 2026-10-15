"""SLSsteam itself is linux only. on windows its ports live here.

HubCapTools is the one that exists: a steam DLL proxy that drops `dwmapi.dll` next to steam.exe
and loads alongside the client. it keeps its own config under <steamdir>/config/hubcaptools, with
its ticket cache one level down in cache/.

what paws can genuinely do for it, without guessing:
  - find it, and see whether the dll is actually sitting next to steam.exe
  - fetch the installer from the repo, verify it against a known sha256, and run it
  - remove the dll and its config

what it can't: OpenValve isn't out yet, and nothing describes how to drive HubCapTools' manifest
generator from outside its own app. `blocked()` names those gaps instead of pretending."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

# the installer lives in the repo root rather than a github release, so the release picker in
# sls/release.py can't see it - the file is found by listing the repo through the contents api
HUB_CAP_REPO = "one-eyed-queen/HubCapTools"
HUB_CAP_CONTENTS_API = f"https://api.github.com/repos/{HUB_CAP_REPO}/contents"
HUB_CAP_RAW = f"https://raw.githubusercontent.com/{HUB_CAP_REPO}/main"
# HubcapTools_Setup_<date>_<shortsha>.exe -> the short sha is the version the site quotes
SETUP_NAME = re.compile(r"^HubcapTools_Setup_(\d{4}-\d{2}-\d{2})_([0-9a-f]{7,40})\.exe$", re.I)
DLL_NAME = "dwmapi.dll"
CONFIG_DIRNAME = "hubcaptools"

UNDER_CONSTRUCTION = (
    "windows support is under construction: installing, updating, removing and activating with SLSsteam's windows "
    "ports (HubCapTools, OpenValve) comes once we know how they work. adding games to the config works already"
)
# what still works on windows without a port. everything else is blocked on how HubCapTools and
# OpenValve install themselves
WORKS_WITHOUT_PORT = (
    "reading and editing config.yaml, adding games, decryption keys, manifests, tokens and dlc, "
    "importing dropped .lua/.key/.manifest files and bundles, the ticket cache, doctor, fix and settings"
)
BLOCKED_WITHOUT_PORT = "installing, updating, removing, and generating tickets"


def blocked(what: str | None = None):
    """the SlsError for 'paws doesn't know how to do this on windows yet', naming the gap and
    what does work, so a user can tell 'paws is broken' from 'paws knows it doesn't know'"""
    from ..sls.errors import SlsError

    return SlsError(
        f"{what + ': ' if what else ''}{UNDER_CONSTRUCTION}\nblocked here: {BLOCKED_WITHOUT_PORT}\nworks now: {WORKS_WITHOUT_PORT}"
    )


def unsupported(what: str | None = None):
    raise blocked(what)


# --------------------------------------------------------------------------- locating


def openvalve_config() -> Path:
    """OpenValve keeps the standard SLSsteam config, at the standard place: %AppData%/SLSsteam/
    config.yaml. it's a manager only - there is nothing to download and nothing to unpack, so
    paws never installs or updates it, it just has to read and write that file"""
    from ..paths import default_config_dir

    return Path(default_config_dir()) / "config.yaml"


def detect(st=None) -> str | None:
    """which windows port is actually present: "hubcaptools", "openvalve", or None.

    the two live in different places on purpose - HubCapTools keeps its own folder next to steam,
    OpenValve uses the normal %AppData% config - so telling them apart never needs a guess.
    """
    dll = proxy_dll(st)
    if dll and dll.exists():
        return "hubcaptools"
    directory = config_dir(st)
    if directory and directory.exists():
        return "hubcaptools"
    cfg = openvalve_config()
    try:
        if cfg.exists():
            return "openvalve"
    except OSError:
        pass
    return None


def config_dir(st=None) -> Path | None:
    """<steamdir>/config/hubcaptools - where the port keeps its config and its ticket cache"""
    from ..steam.find import find_steam

    st = st or find_steam()
    if not st or not st.root:
        return None
    return Path(st.root) / "config" / CONFIG_DIRNAME


def proxy_dll(st=None) -> Path | None:
    """the dll the port loads with. it sits next to steam.exe, which is the whole proxy trick"""
    from ..steam.find import find_steam

    st = st or find_steam()
    if not st or not st.root:
        return None
    return Path(st.root) / DLL_NAME


def find(config: Path | None = None):
    """the port, located by where it actually keeps its config rather than by guessing dll names"""
    from ..sls.model import SlsInstall
    from ..util import fs

    which = detect()
    if which == "hubcaptools":
        directory = config_dir()
        if directory is None:
            return None
        cfg = directory / "config.yaml"
        sls = SlsInstall(kind="windows", config=cfg if fs.exists(cfg) else None)
        sls.cache, sls.plugins = directory / "cache", directory / "plugins"
        sls.lib_dir = directory
        sls.port = "hubcaptools"
        return sls
    if which == "openvalve":
        cfg = openvalve_config()
        sls = SlsInstall(kind="windows", config=cfg)
        sls.cache, sls.plugins = cfg.parent / "cache", cfg.parent / "plugins"
        sls.lib_dir = cfg.parent
        sls.port = "openvalve"
        return sls
    return None


def injected(st=None) -> bool:
    """whether the dll is actually in place. that is the only honest signal available - there is no
    way yet to ask a running client what it loaded"""
    dll = proxy_dll(st)
    return bool(dll and dll.exists())


def status(st=None, check_latest: bool = False) -> dict:
    """what paws can actually see, for the ui and for doctor.

    check_latest is off by default on purpose: doctor runs this, and it should never block on
    github being reachable. callers that want the newest build ask for it explicitly.
    """
    directory, dll = config_dir(st), proxy_dll(st)
    which = detect(st)
    return {
        "port": which,
        "config_dir": directory,
        "installed": bool(dll and dll.exists()),
        "dll": dll,
        "has_config": bool(directory and directory.exists()),
        "openvalve_config": openvalve_config() if which == "openvalve" else None,
        "version": installed_version(),
        "latest": latest_version() if check_latest else None,
    }


# --------------------------------------------------------------------------- versions


def latest_asset(timeout: float = 15.0) -> tuple[str, str] | None:
    """(filename, version) for the newest installer in the repo, or None when github can't be reached"""
    request = urllib.request.Request(HUB_CAP_CONTENTS_API, headers={"User-Agent": "paws"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            entries = json.loads(r.read().decode())
    except Exception:
        return None
    best = None
    for entry in entries if isinstance(entries, list) else []:
        m = SETUP_NAME.match(str(entry.get("name", "")))
        if not m:
            continue
        date, sha = m.group(1), m.group(2)
        if best is None or date > best[0]:
            best = (date, sha, str(entry.get("name")))
    return (best[2], best[1]) if best else None


def latest_version(timeout: float = 15.0) -> str | None:
    found = latest_asset(timeout)
    return found[1] if found else None


def installed_version() -> str | None:
    """the version paws last installed, recorded next to the dll so it survives steam moving things"""
    marker = _marker()
    if marker is None or not marker.exists():
        return None
    try:
        return marker.read_text().strip() or None
    except OSError:
        return None


def _marker() -> Path | None:
    from ..paths import default_config_dir

    return Path(default_config_dir()) / "hubcaptools-version"


# --------------------------------------------------------------------------- install


def download_installer(dest_dir: Path, progress=None, timeout: float = 30.0) -> Path | None:
    """fetch the newest installer into dest_dir. returns the path, or None when the repo can't be read"""
    found = latest_asset(timeout)
    if not found:
        return None
    name, _version = found
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / name
    request = urllib.request.Request(f"{HUB_CAP_RAW}/{name}", headers={"User-Agent": "paws"})
    try:
        with urllib.request.urlopen(request, timeout=120) as r, open(target, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def expected_sha256(version: str | None) -> str | None:
    """the sha256 paws knows for a given HubCapTools build. None means 'nothing pinned for this
    build', which callers must treat as unverified rather than as fine"""
    return KNOWN_SHA256.get((version or "").lower())


# hashes for builds paws has actually checked against the vendor's published value. a build that
# isn't in here is new to paws: it can still be installed, but only after the user is told the
# download can't be verified - it ends up as a dll next to steam.exe, so that has to be a
# deliberate decision and not a silent one
KNOWN_SHA256 = {
    "056be3c": "7f885040a37e503e5521a15c011a3ee9a1732b38818efa158e3c7ed74259a2b8",
}


def verify(path: Path, version: str | None = None) -> bool:
    """True only when the file matches a hash paws has pinned for that exact build"""
    digest = expected_sha256(version)
    if not digest:
        return False
    from ..sls.archive import file_sha256

    try:
        return file_sha256(path).lower() == digest.lower()
    except OSError:
        return False


def sha256_of(path: Path) -> str | None:
    from ..sls.archive import file_sha256

    try:
        return file_sha256(path)
    except OSError:
        return None


def run_installer(path: Path) -> None:
    """hand the installer to windows. steam has to be closed first - the dll goes next to a running
    steam.exe and the client caches what it loaded, so the write would be ignored"""
    from .process import steam_running

    if steam_running():
        raise blocked(
            "close steam completely first, then run this again - HubCapTools writes next to steam.exe and steam ignores it while running"
        )
    try:
        subprocess.run([str(path)], check=False)
    except OSError as error:
        raise blocked(f"couldn't start the HubCapTools installer: {error}") from error


def record_version(version: str) -> None:
    marker = _marker()
    if marker is None:
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(version)
    except OSError:
        pass


def remove(st=None) -> list[str]:
    """take away only what paws can positively claim.

    HubCapTools owns exactly two things here: the proxy dll next to steam.exe and its own config
    folder. OpenValve owns a config folder in %AppData% that paws did not create - deleting
    someone's app config because it happens to sit in the standard place would be wrong, so that
    is left alone and only reported.
    """
    removed, skipped = [], []
    dll = proxy_dll(st)
    if dll and dll.exists():
        try:
            dll.unlink()
            removed.append(str(dll))
        except OSError:
            pass
    directory = config_dir(st)
    if directory and directory.exists():
        try:
            shutil.rmtree(directory)
            removed.append(str(directory))
        except OSError:
            pass
    marker = _marker()
    if marker and marker.exists():
        try:
            marker.unlink()
        except OSError:
            pass
    cfg = openvalve_config()
    try:
        if cfg.exists():
            skipped.append(f"{cfg} (OpenValve's own config - paws did not create it, so it stays)")
    except OSError:
        pass
    removed.extend(skipped)
    return removed
