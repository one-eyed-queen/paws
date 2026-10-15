from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from ..paths import HOME, default_config_dir
from . import private
from .archive import extract_archive, file_sha256, stage_inner
from .desktop import write_launcher
from .errors import SlsError
from .find import INJECT_NAMES, LIB_NAMES, find_sls
from .model import SlsInstall
from .release import SlsSource, download, resolve_source


def merge_user_config(release, user_config_path):
    from .. import config

    if not user_config_path.exists():
        release_config = release / "res" / "config.yaml"
        if release_config.exists():
            shutil.copy2(release_config, user_config_path)
        else:
            user_config_path.write_text(config.default_config_text())
    config.fill_missing(user_config_path)


def install_port(progress=None, allow_unverified: bool = False) -> SlsInstall:
    """windows path. only HubCapTools has something to install - OpenValve is a manager with no
    download and no source, so paws never tries to fetch it, it just reads and writes the config
    it already keeps in the normal place.

    for HubCapTools: fetch the installer, check it, hand it to windows.

    the installer is the vendor's own and drops dwmapi.dll next to steam.exe, so this refuses to
    guess: steam has to be shut, and the download has to match a hash paws has pinned for that
    build unless the caller explicitly accepts an unverified one.
    """
    from ..paths import HOME
    from ..windows import port

    existing = port.find()
    if existing is not None and existing.port == "openvalve":
        raise SlsError(
            f"OpenValve is already managing {existing.config} - it's a manager, so there's nothing to install.\n"
            "paws reads and writes that config directly: drop a .lua/.key/.manifest, or use Add game."
        )
    if existing is not None and port.injected():
        raise SlsError(
            f"HubCapTools is already installed ({port.proxy_dll()}) - use Update if you want the newest build"
        )

    found = port.latest_asset()
    if not found:
        raise SlsError(f"couldn't read {port.HUB_CAP_REPO} - is github reachable?")
    name, version = found
    installer = port.download_installer(HOME / ".cache/paws", progress)
    if installer is None or not installer.exists():
        raise SlsError(f"couldn't download {name}")
    try:
        if not port.verify(installer, version):
            digest = port.sha256_of(installer)
            pinned = port.expected_sha256(version)
            if pinned:
                raise SlsError(
                    f"{name} doesn't match the checksum paws has for {version}\n"
                    f"  expected {pinned}\n  got      {digest}\nrefusing to run it"
                )
            if not allow_unverified:
                raise SlsError(
                    f"{name} is a build paws has no checksum for ({version}, sha256 {digest}).\n"
                    "it would be written next to steam.exe, so paws won't run it unchecked - "
                    "re-run with --allow-unverified if you trust it."
                )
        port.run_installer(installer)
    finally:
        installer.unlink(missing_ok=True)
    port.record_version(version)
    sls = port.find()
    if sls is None:
        raise SlsError("the installer finished but paws can't see the result - is steam in the usual place?")
    return sls


def update_port(progress=None, allow_unverified: bool = False) -> tuple[SlsInstall, bool]:
    """like install_port, but tells the caller whether there was anything to do"""
    from ..windows import port

    existing = port.find()
    if existing is not None and existing.port == "openvalve":
        # manager only: no version to compare and nothing to fetch. don't pretend otherwise
        return existing, False
    latest = port.latest_version()
    current = port.installed_version()
    if current and latest and current == latest and existing is not None:
        return existing, False
    return install_port(progress, allow_unverified), True


def install_release(
    source: SlsSource,
    destination: Path | None = None,
    write_desktop: bool = True,
    merge_config: bool = True,
    progress=None,
    allow_unverified: bool = False,
) -> SlsInstall:
    from ..windows import IS_WINDOWS

    if IS_WINDOWS:
        return install_port(progress, allow_unverified)
    destination = destination or HOME / ".local/share/SLSsteam"
    download_dir = HOME / ".cache/paws"
    if source.kind == "private":
        if not source.url:
            raise SlsError("a private build needs a repo link or a .zip/.7z file")
        archive, name, downloaded = private.fetch(source.url, download_dir, progress)
    elif source.kind == "local":
        archive = Path(source.url or "").expanduser()
        if not archive.is_file():
            raise SlsError(f"local file not found: {archive}")
        name, downloaded = source.name, False
    else:
        url, name = resolve_source(source)
        archive = download(url, download_dir, progress)
        downloaded = True
    staging = download_dir / f"paws-stage-{int(time.time())}"
    try:
        return _install_staged(source, name, archive, staging, destination, write_desktop, merge_config)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if downloaded:
            archive.unlink(missing_ok=True)


def _find_libs(root: Path) -> tuple[list[Path], Path]:
    """the actual SLSsteam libraries, wherever this build put them.

    the two builds are laid out differently and guessing produced a silently broken install:

        SLSsteam-Any-*.7z            bin/SLSsteam.so, bin/library-inject.so, tools/, res/
        SLSsteam-Arch-*.pkg.tar.zst  usr/lib32/libSLSsteam.so, usr/lib32/libSLS-library-inject.so,
                                    usr/bin/*-grabber, usr/share/...

    taking "everything in bin/" grabbed the ticket and schema grabbers from the arch package and
    called them the library. so the library is found by name, in the places either layout puts it.
    returns (libs, the prefix they were found under).
    """
    names = {n.lower() for n in LIB_NAMES + INJECT_NAMES}  # shared with find.py, so both agree
    search = [
        root / "bin",
        root,
        root / "usr" / "lib32",
        root / "usr" / "lib64",
        root / "usr" / "lib",
        root / "lib32",
        root / "lib64",
        root / "lib",
    ]
    for prefix in search:
        if not prefix.is_dir():
            continue
        found = [f for f in sorted(prefix.iterdir()) if f.is_file() and f.suffix == ".so" and f.name.lower() in names]
        if found:
            return found, prefix
    # last resort: the portable build's flat "*.so at the root" layout
    flat = sorted(p for p in root.glob("*.so") if p.is_file())
    return flat, root


def _install_staged(
    source,
    name,
    archive,
    staging,
    destination,
    write_desktop,
    merge_config,
):
    extract_archive(archive, staging)
    inner = stage_inner(staging)
    libs, layout = _find_libs(inner)
    if not libs:
        raise SlsError(f"{archive.name} has no built library in it (a bin/ folder or .so files): source code won't do")
    destination.mkdir(parents=True, exist_ok=True)
    for lib in libs:
        shutil.copy2(lib, destination / lib.name)
    # the portable .7z keeps its helpers in tools/ and its template in res/. the arch package puts
    # the grabbers in usr/bin and ships no res/ at all, so both are looked for rather than assumed
    tools_source = next((p for p in (inner / "tools", layout / "bin") if p.is_dir()), None)
    if tools_source is not None:
        tools_destination = destination / "tools"
        shutil.rmtree(tools_destination, ignore_errors=True)
        shutil.copytree(tools_source, tools_destination)
    res_source = next((p for p in (inner / "res", layout / "share" / "slssteam") if p.is_dir()), None)
    if res_source is not None:
        res_destination = destination / "res"
        shutil.rmtree(res_destination, ignore_errors=True)
        shutil.copytree(res_source, res_destination)
    docs_source = inner / "docs" / "LICENSE"
    if docs_source.exists():
        shutil.copytree(docs_source, destination / "docs" / "LICENSE", dirs_exist_ok=True)
    if merge_config:
        config_dir = default_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        merge_user_config(inner, config_dir / "config.yaml")
    info = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": source.kind,
        "source_desc": source.describe(),
        "tag": name if source.kind in ("github", "forgejo", "private") else None,
        "sha256": file_sha256(archive),
        "files": [f.name for f in destination.iterdir() if f.is_file()],
    }
    (destination / "paws.info.json").write_text(json.dumps(info, indent=2))

    if write_desktop:
        write_launcher(destination)

    return find_sls()
