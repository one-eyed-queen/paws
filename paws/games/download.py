"""how a game you want to download goes in the config.

public SLSsteam can't download at all (its author: "adding apps only needs AdditionalApps. downloading needs some
more" / "public SLS can't download"): there AdditionalApps is the only way a game shows up, and it stays at 0 B.
steam also has to ask valve for every depot's manifest request code, valve answers "Access Denied" for a game you
don't own, and steam shows that as "no internet connection". private builds fetch that code themselves.

private builds from 2026-11 read AdditionalPackageApps, their own template: "Additional apps to inject into package 0.
Use this instead of AdditionalApps for every game you want to download via the Steam client itself". older private
builds read AdditionalPackages (the game's store package) and AdditionalDepots instead.

the public build downloads too with SLSsteam's download plugin (sls/plugins.py): it reads AdditionalDepots and
DecryptionKeys itself and fetches the manifest request codes, so with it the game stays in AdditionalApps and its
keyed depots go in AdditionalDepots, the way the SLSsteam author's own convert-lua writes them.

SLSsteam's AdditionalApps overrides the game's owner, and with DisableUpdates on it also makes steam's update info for
that app fail (Apps::shouldDisableUpdates, hooks.cpp GetAppUpdateInfo). steam then has nothing to download and shows
0 B. builds that read AdditionalPackages can give the game a real license instead: its store package plus its AppIds
row (with UseWhitelist on) and the depot keys. so a game with a store package goes in that way, and AdditionalApps is
only the fallback for games with no package or a build that doesn't know AdditionalPackages."""

from __future__ import annotations

from pathlib import Path

ACTIVATION_NOTE = "activated"  # activation's own short-lived rows, never touched here


_SUPPORT: dict = {}


def build_keys() -> frozenset[str]:
    """the PRIVATE_ONLY keys something in this SLSsteam reads: the .so itself, or a lua plugin it runs"""
    try:
        from ..sls.plugins import keys_read

        extra = keys_read() & frozenset(PRIVATE_ONLY)
    except Exception:
        extra = frozenset()
    return so_keys() | extra


def so_keys() -> frozenset[str]:
    """the PRIVATE_ONLY keys the installed SLSsteam .so reads, asked of the binary itself: a build that reads a key
    has its name in it. its res/config.yaml template isn't proof either way, and neither is the config"""
    try:
        from ..sls.find import find_sls

        sls = find_sls()
        so = Path(sls.sls_so) if sls and sls.sls_so else None
        if so is None or not so.is_file():
            return frozenset()  # a config alone says nothing about the build, and unblock() takes rows out on a yes
        stamp = (str(so), so.stat().st_mtime_ns)
        if stamp not in _SUPPORT:
            content = so.read_bytes()
            _SUPPORT[stamp] = frozenset(k for k in PRIVATE_ONLY if k.encode() in content)
        return _SUPPORT[stamp]
    except Exception:
        return frozenset()


def reads(key: str) -> bool:
    return key in build_keys()


def packages_supported() -> bool:
    """is the installed SLSsteam .so a private build, one that downloads by itself? the public one reads none of
    PRIVATE_ONLY. a download plugin doesn't count here: with it the game still goes in through AdditionalApps"""
    return bool(so_keys() & {"AdditionalPackages", "AdditionalPackageApps", "DecryptionKeys"})


def plugin_downloads() -> bool:
    """a public build that downloads through SLSsteam's download plugin"""
    if packages_supported():
        return False
    try:
        from ..sls.plugins import download_ready

        return download_ready()
    except Exception:
        return False


def can_download() -> bool:
    return packages_supported() or plugin_downloads()


# config keys only private builds read (checked against public 20261106120254 and the 2026-09 and 2026-11 private .so);
# everything else is shared — FakeAppIds, CDKeys, SteamIdOverride, FakeName, Plugins, SmartTickets are all in public.
# 2026-11 private dropped AdditionalDepots and added AdditionalPackageApps
PRIVATE_ONLY = (
    "AdditionalPackageApps",
    "AdditionalPackages",
    "DecryptionKeys",
    "AdditionalDepots",
    "CloudProxies",
    "InventoryItems",
)


def known_build() -> bool:
    """is there an installed SLSsteam .so to ask? a config alone says nothing about the build"""
    try:
        from ..sls.find import find_sls

        sls = find_sls()
        return bool(sls and sls.sls_so and Path(sls.sls_so).is_file())
    except Exception:
        return False


def build_reads(key: str) -> bool:
    """would the installed SLSsteam read this config key? unknown build (none installed): assume yes"""
    return key not in PRIVATE_ONLY or not known_build() or reads(key)


def drop_private_sections(config_path=None) -> list[str]:
    """public build: the private-only sections do nothing there, so they go. their keys are kept first (paws' own
    store, and steam's config.vdf where they actually work). a section a live plugin reads stays: that's the
    download plugin's data, and an installer that takes it out breaks every download.
    returns the sections removed"""
    from .. import config
    from ..util import backup
    from ..config.io import raw_lines, write
    from ..config.lines import block_end_line, section_index

    if not known_build() or packages_supported():
        return []
    path = config_path or config.find_config()
    if path is None:
        return []
    data = config.parsed(path)
    keys = {str(d): str(k).strip('"') for d, k in (data.get("DecryptionKeys") or {}).items() if k}
    if keys:
        from ..steam.sync import remember_keys

        remember_keys(keys)
    lines = raw_lines(path)
    gone, drop = [], set()
    for name in PRIVATE_ONLY:
        index = section_index(lines, name)
        if index is None or reads(name):
            continue
        end = block_end_line(lines, index)
        start = index
        while start > 0 and lines[start - 1].lstrip().startswith("#") and section_index(lines[start - 1 : start], name) is None:
            start -= 1  # its own comment lines above it go too
        drop.update(range(start, end))
        gone.append(name)
    if not gone:
        return []
    backup.backup_file(path)
    kept = [l for i, l in enumerate(lines) if i not in drop]
    while kept and kept[-1].strip() in ("", "# --- added by paws: keys SLSsteam expects ---"):
        kept.pop()
    write(path, "\n".join(kept) + "\n")
    return gone


def blocked_rows(text: str) -> list[tuple[int, str, str]]:
    """(line number, appid, name) for AdditionalApps rows of games that also have their AppIds row: added for a
    download, and that row is what keeps them at 0 B"""
    from ..config.lines import _code_part, block_end_line, item_key, section_index
    from ..config.tidy import split_comment

    lines = text.splitlines()
    index = section_index(lines, "AdditionalApps")
    if index is None:
        return []
    allowed = section_index(lines, "AppIds")
    whitelisted = set()
    if allowed is not None:
        whitelisted = {item_key(l) for l in lines[allowed + 1 : block_end_line(lines, allowed)] if _code_part(l).strip()}
    out = []
    for i in range(index + 1, block_end_line(lines, index)):
        if not _code_part(lines[i]).strip():
            continue
        appid = item_key(lines[i])
        name = split_comment(lines[i])[1]
        if appid and appid in whitelisted and not name.startswith(ACTIVATION_NOTE):
            out.append((i, str(appid), name))
    return out


def unblock(config_path=None) -> list[str]:
    """moves those games over: into AdditionalPackageApps where the build reads it, else their store package in, and
    the AdditionalApps row out. only with steam closed, because a row disappearing while it runs can make steam
    uninstall the game. returns the games it moved"""
    from .. import config
    from ..config.io import raw_lines, write
    from ..sources import from_store
    from ..steam import is_running
    from ..util import backup

    if is_running() or not packages_supported():
        return []
    path = config_path or config.find_config()
    if path is None:
        return []
    text = "\n".join(raw_lines(path)) + "\n"
    if reads("AdditionalPackageApps"):
        moved = {appid: name or appid for _line, appid, name in blocked_rows(text)}
        if not moved:
            return []
        backup.backup_file(path)
        with config.batch():
            for appid, name in moved.items():
                line = config.render_item("AdditionalPackageApps", id=appid, name=name)
                config.add_entry("AdditionalPackageApps", line, backup=False)
            lines = raw_lines(path)
            drop = {i for i, appid, _name in blocked_rows("\n".join(lines) + "\n") if appid in moved}
            write(path, "\n".join(l for i, l in enumerate(lines) if i not in drop) + "\n")
        return list(moved.values())
    packages = {}
    for _line, appid, name in blocked_rows(text):
        try:
            info = from_store(appid)
        except Exception:
            continue  # offline: leave it for next time
        if info.packages:
            packages[appid] = (str(info.packages[0]), name or info.name or appid)
    if not packages:
        return []
    backup.backup_file(path)
    with config.batch():
        for appid, (package, name) in packages.items():
            config.add_entry("AdditionalPackages", config.render_item("AdditionalPackages", id=package, name=name), backup=False)
        lines = raw_lines(path)
        drop = {i for i, appid, _name in blocked_rows("\n".join(lines) + "\n") if appid in packages}
        write(path, "\n".join(l for i, l in enumerate(lines) if i not in drop) + "\n")
    return [name for _package, name in packages.values()]
