"""how a game you want to download goes in the config.

public SLSsteam can't download at all (its author: "adding apps only needs AdditionalApps. downloading needs some
more" / "public SLS can't download"): there AdditionalApps is the only way a game shows up, and it stays at 0 B.
the private build reads AdditionalPackages and DecryptionKeys, and that's the way to download.

SLSsteam's AdditionalApps overrides the game's owner, and with DisableUpdates on it also makes steam's update info for
that app fail (Apps::shouldDisableUpdates, hooks.cpp GetAppUpdateInfo). steam then has nothing to download and shows
0 B. builds that read AdditionalPackages can give the game a real license instead: its store package plus its AppIds
row (with UseWhitelist on) and the depot keys. so a game with a store package goes in that way, and AdditionalApps is
only the fallback for games with no package or a build that doesn't know AdditionalPackages."""

from __future__ import annotations

from pathlib import Path

ACTIVATION_NOTE = "activated"  # activation's own short-lived rows, never touched here


_SUPPORT: dict = {}


def packages_supported() -> bool:
    """does the installed SLSsteam read AdditionalPackages? asked of the .so itself: a build that reads a key has its
    name in the binary (the public build 20261014151919 has AdditionalApps/AppIds/ManifestIds and no
    AdditionalPackages or DecryptionKeys). its res/config.yaml template isn't proof either way"""
    try:
        from ..sls.find import find_sls

        sls = find_sls()
        so = Path(sls.sls_so) if sls and sls.sls_so else None
        if so is None or not so.is_file():
            return False
        stamp = (str(so), so.stat().st_mtime_ns)
        if stamp not in _SUPPORT:
            _SUPPORT[stamp] = b"AdditionalPackages" in so.read_bytes()
        return _SUPPORT[stamp]
    except Exception:
        return False


# config keys only the private build reads (checked against both builds' .so on 2026-11-07); everything else is shared
PRIVATE_ONLY = ("AdditionalPackages", "DecryptionKeys", "AdditionalDepots", "CloudProxies", "InventoryItems")


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
    return key not in PRIVATE_ONLY or not known_build() or packages_supported()


def drop_private_sections(config_path=None) -> list[str]:
    """public build: the private-only sections do nothing there, so they go. their keys are kept first (paws' own
    store, and steam's config.vdf where they actually work). returns the sections removed"""
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
        if index is None:
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
    """moves those games over: their store package in, the AdditionalApps row out. only with steam closed, because
    a row disappearing while it runs can make steam uninstall the game. returns the games it moved"""
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
