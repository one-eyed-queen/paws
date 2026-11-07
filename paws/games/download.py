"""how a game you want to download goes in the config.

SLSsteam's AdditionalApps overrides the game's owner, and with DisableUpdates on it also makes steam's update info for
that app fail (Apps::shouldDisableUpdates, hooks.cpp GetAppUpdateInfo). steam then has nothing to download and shows
0 B. builds that read AdditionalPackages can give the game a real license instead: its store package plus its AppIds
row (with UseWhitelist on) and the depot keys. so a game with a store package goes in that way, and AdditionalApps is
only the fallback for games with no package or a build that doesn't know AdditionalPackages."""

from __future__ import annotations

ACTIVATION_NOTE = "activated"  # activation's own short-lived rows, never touched here


def packages_supported() -> bool:
    """does the installed SLSsteam read AdditionalPackages? its own config template says so, or the config has the key"""
    try:
        from ..config.upstream import installed_template_keys
        from ..sls.find import find_sls

        sls = find_sls()
        keys = installed_template_keys(sls.lib_dir if sls else None)
        if keys is not None:
            return "AdditionalPackages" in keys
    except Exception:
        pass
    try:
        from .. import config

        return "AdditionalPackages" in (config.parsed() or {})
    except Exception:
        return False


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
