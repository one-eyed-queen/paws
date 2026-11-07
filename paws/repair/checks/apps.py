"""AdditionalApps is how SLSsteam injects an app you don't own into your library: it appends the
list to the apps steam thinks you're subscribed to, and that is the only way an unowned game ever
shows up. so those rows are load-bearing and must stay.

what breaks is the same row for an app steam already lists for you: AdditionalApps overrides that
app's owner id, downloads fail and steam can loop on "loading user data". that is the only kind of
row this check takes out, and only with steam closed (removing one live can make steam uninstall
the game, because SLSsteam reports its license as changed)"""

from __future__ import annotations

from pathlib import Path

from ...config.io import write_now
from ...config.lines import _code_part, block_end_line, item_key, section_index
from ...util import backup
from ..model import Problem
from ._shared import safe_read


def _ids(lines, section):
    index = section_index(lines, section)
    if index is None:
        return set()
    return {item_key(l) for l in lines[index + 1 : block_end_line(lines, index)] if _code_part(l).strip()} - {None}


def leftovers(text: str, owned: set[str] | None = None) -> dict[int, tuple[str, str]]:
    """line number -> (appid, why) for every AdditionalApps row that is doing harm.

    a row for a game you don't own is what keeps it in your library, so it is never touched here.
    only rows for apps steam already lists for you come out, because those override the owner id
    without adding anything."""
    lines = text.splitlines()
    index = section_index(lines, "AdditionalApps")
    if index is None:
        return {}
    if owned is None:
        try:
            from ...steam.library import owned_appids

            owned = owned_appids()
        except (ImportError, OSError):
            owned = set()
    owned = {str(a) for a in owned}
    out = {}
    for i in range(index + 1, block_end_line(lines, index)):
        line = lines[i]
        appid = item_key(line) if _code_part(line).strip() else None
        if appid is None or str(appid) not in owned:
            continue
        out[i] = (appid, "steam already lists it for you, so this only overrides the owner id")
    return out


def strip_rows(text: str, rows) -> str:
    lines = text.splitlines()
    return "\n".join(l for i, l in enumerate(lines) if i not in rows) + "\n"


def check_additional_apps(config_path: Path) -> list[Problem]:
    text = safe_read(config_path)
    found = leftovers(text) if text is not None else {}
    if not found:
        return []

    owned = {a for a, _ in found.values()}

    def fix() -> str:
        from ...steam import is_running

        if is_running():
            return "close steam first: taking these out while it runs can make it uninstall the games. nothing changed"
        now = safe_read(config_path) or ""
        rows = leftovers(now, owned)
        backup.backup_file(config_path)
        write_now(config_path, strip_rows(now, rows))
        return f"took {len(rows)} row(s) out of AdditionalApps ({', '.join(a for a, _ in rows.values())}); backup kept"

    listed = ", ".join(f"{appid} ({why})" for appid, why in list(found.values())[:6])
    return [
        Problem(
            "config.additionalapps-leftovers",
            f"{len(found)} AdditionalApps row(s) that shouldn't be there",
            f"{listed}. these are already in your library, so the row only overrides their owner id: "
            "downloads fail and steam can loop on loading user data",
            "take them out (steam has to be closed; AppIds entries stay)",
            fix,
            "error",
        )
    ]


def bad_packages(text: str, lookup=None, game_package=None) -> tuple[dict[int, tuple[str, str]], dict[str, str]]:
    """AdditionalPackages should hold one thing per game: that game's own store package ("Buy <game>").
    returns (line number -> (package id, why) to take out, package id -> game for packages to put in instead).
    older paws builds wrote every package the store page lists: other editions, add-ons like CS2's Prime upgrade,
    commercial licenses, even other apps (Portal 2 lists The Final Hours). anything the store can't answer for
    is left alone, so being offline never removes a row"""
    from ...sources.store import _package, from_store

    lookup = lookup or _package
    mains: dict[str, tuple[str | None, str]] = {}

    def own(appid):  # (that game's own package or None, its name)
        if appid not in mains:
            try:
                info = game_package(appid) if game_package else from_store(appid)
                mains[appid] = ((info.packages or [None])[0], info.name or appid)
            except Exception:
                mains[appid] = (None, appid)
        return mains[appid]

    lines = text.splitlines()
    index = section_index(lines, "AdditionalPackages")
    if index is None:
        return {}, {}
    games = _ids(lines, "AppIds") | _ids(lines, "AdditionalApps")
    have = _ids(lines, "AdditionalPackages")
    drop, add, touched = {}, {}, set()
    for i in range(index + 1, block_end_line(lines, index)):
        packageid = item_key(lines[i]) if _code_part(lines[i]).strip() else None
        if packageid is None:
            continue
        details = lookup(packageid)
        if details is None:
            continue  # couldn't ask the store
        if not details:
            drop[i] = (packageid, "the store doesn't sell it")
            label = lines[i].partition("#")[2].strip().lower()  # paws wrote the game's name beside it
            touched |= {a for a in games if label and label != packageid and own(a)[1].lower() == label}
            continue
        name = str(details.get("name", "?"))
        mine = [a for a in (str(x.get("id")) for x in details.get("apps", [])) if a in games]
        if "commercial license" in name.lower():
            why = "a commercial license"
        elif not mine:
            why = f"none of your games are in it ({name})"
        elif any(own(a)[0] == packageid for a in mine) or not any(own(a)[0] for a in mine):
            continue  # it IS a game's own package, or the store can't tell us what is
        else:
            why = f"{name}: not the game's own package"
        drop[i] = (packageid, why)
        touched |= set(mine)
    for appid in sorted(touched):  # a game whose wrong packages come out gets its own one instead
        main, name = own(appid)
        if main and main not in have and main not in add:
            add[main] = name
    return drop, add


def apply_packages(text: str, drop, add) -> str:
    lines = text.splitlines()
    index = section_index(lines, "AdditionalPackages")
    kept = [l for i, l in enumerate(lines) if i not in drop]
    if add and index is not None:
        at = index + 1 - sum(1 for i in drop if i < index)
        kept[at:at] = [f"  - {packageid} # {name}" for packageid, name in add.items()]
    return "\n".join(kept) + "\n"


def check_additional_packages(config_path: Path) -> list[Problem]:
    text = safe_read(config_path)
    drop, add = bad_packages(text) if text is not None else ({}, {})
    if not drop:
        return []

    def fix() -> str:
        from ...steam import is_running

        if is_running():
            return "close steam first, it picks license changes up live. nothing changed"
        now = safe_read(config_path) or ""
        drop_now, add_now = bad_packages(now)
        backup.backup_file(config_path)
        write_now(config_path, apply_packages(now, drop_now, add_now))
        added = f", put in {', '.join(add_now)} (the game's own package)" if add_now else ""
        return f"took {len(drop_now)} package(s) out ({', '.join(p for p, _ in drop_now.values())}){added}; backup kept"

    listed = "; ".join(f"{packageid} ({why})" for packageid, why in list(drop.values())[:8])
    more = f"; then add {', '.join(f'{p} ({n})' for p, n in add.items())}" if add else ""
    return [
        Problem(
            "config.additionalpackages-wrong",
            f"{len(drop)} AdditionalPackages row(s) with the wrong license",
            f"{listed}{more}. only a game's own store package belongs there, others can loop steam on loading user data",
            "take them out and keep one store package per game (steam has to be closed)",
            fix,
            "error",
        )
    ]


def check_downloads_blocked(config_path: Path) -> list[Problem]:
    """games added for download that still carry an AdditionalApps row: steam shows them at 0 B and won't download"""
    from ...games.download import blocked_rows, packages_supported, unblock

    text = safe_read(config_path)
    rows = blocked_rows(text) if text is not None and packages_supported() else []
    if not rows:
        return []

    def fix() -> str:
        from ...steam import is_running

        if is_running():
            return "close steam first: taking these out while it runs can make it uninstall the games. nothing changed"
        moved = unblock(config_path)
        if not moved:
            return "couldn't reach the store for their packages, nothing changed. try again online"
        return f"moved {len(moved)} game(s) to their store package: {', '.join(moved)}. backup kept"

    listed = ", ".join(name or appid for _i, appid, name in rows[:6])
    return [
        Problem(
            "config.downloads-blocked",
            f"{len(rows)} game(s) can't download (0 B in steam)",
            f"{listed}. their AdditionalApps row overrides the owner, and with DisableUpdates it hides the download",
            "give each its store package and take the AdditionalApps row out (steam has to be closed)",
            fix,
            "error",
        )
    ]


def check_steam_sync(config_path: Path) -> list[Problem]:
    """keys or manifests config.yaml has and steam doesn't: every game they belong to shows 0 B"""
    from ...steam.sync import find_files, missing, restore

    try:
        keys, manifests = missing()
    except Exception:
        return []
    if not keys and not manifests:
        return []

    def fix() -> str:
        result = restore()
        if result.get("error") == "steam is running":
            return "close steam first: it rewrites config.vdf on exit and would drop the keys again. nothing changed"
        if result.get("error"):
            return f"couldn't write config.vdf: {result['error']}"
        lost = result.get("not_found") or []
        tail = f". {len(lost)} manifest(s) aren't anywhere on this pc: drop those games' files again" if lost else ""
        return f"put {result['keys']} key(s) and {result['manifests']} manifest(s) back in steam{tail}"

    findable = len(find_files(manifests)) if manifests else 0
    return [
        Problem(
            "steam.keys-manifests-missing",
            f"steam is missing {len(keys)} key(s) and {len(manifests)} manifest(s) from your config",
            "steam was moved or reinstalled, so games show 0 B and won't download. "
            f"the keys come from config.yaml; {findable} of the {len(manifests)} manifest(s) can be found on this pc",
            "put them back into steam's config.vdf and depotcache (steam has to be closed)",
            fix,
            "error",
        )
    ]
