"""AdditionalApps overwrites a game's owner id. fine for a game you only play, but it breaks downloads and can leave
steam looping on "loading user data". two kinds of rows paws can spot for sure:
  - `# activated N` rows older paws builds left behind after making tickets
  - games that are in AppIds too (adding a game puts it in AppIds, never both)
taking a row out while steam runs can make steam uninstall that game (SLSsteam reports its license as changed), so
the fix only runs with steam closed: SLSsteam's first load doesn't compare against the old list"""

from __future__ import annotations

import re
from pathlib import Path

from ...config.io import write_now
from ...config.lines import _code_part, block_end_line, item_key, section_index
from ...util import backup
from ..model import Problem
from ._shared import safe_read

ACTIVATED = re.compile(r"#\s*activated\s+\d+")


def _ids(lines, section):
    index = section_index(lines, section)
    if index is None:
        return set()
    return {item_key(l) for l in lines[index + 1 : block_end_line(lines, index)] if _code_part(l).strip()} - {None}


def leftovers(text: str) -> dict[int, tuple[str, str]]:
    """line number -> (appid, why) for every AdditionalApps row that shouldn't be there"""
    lines = text.splitlines()
    index = section_index(lines, "AdditionalApps")
    if index is None:
        return {}
    in_app_ids = _ids(lines, "AppIds")
    out = {}
    for i in range(index + 1, block_end_line(lines, index)):
        line = lines[i]
        appid = item_key(line) if _code_part(line).strip() else None
        if appid is None:
            continue
        if ACTIVATED.search(line):
            out[i] = (appid, "left over from making tickets")
        elif appid in in_app_ids:
            out[i] = (appid, "also in AppIds")
    return out


def strip_rows(text: str, rows) -> str:
    lines = text.splitlines()
    return "\n".join(l for i, l in enumerate(lines) if i not in rows) + "\n"


def check_additional_apps(config_path: Path) -> list[Problem]:
    text = safe_read(config_path)
    found = leftovers(text) if text is not None else {}
    if not found:
        return []

    def fix() -> str:
        from ...steam import is_running

        if is_running():
            return "close steam first: taking these out while it runs can make it uninstall the games. nothing changed"
        now = safe_read(config_path) or ""
        rows = leftovers(now)
        backup.backup_file(config_path)
        write_now(config_path, strip_rows(now, rows))
        return f"took {len(rows)} row(s) out of AdditionalApps ({', '.join(a for a, _ in rows.values())}); backup kept"

    listed = ", ".join(f"{appid} ({why})" for appid, why in list(found.values())[:6])
    return [
        Problem(
            "config.additionalapps-leftovers",
            f"{len(found)} AdditionalApps row(s) that break downloads",
            f"{listed}. AdditionalApps overwrites the owner id: downloads fail and steam can loop on loading user data",
            "take them out of AdditionalApps (steam has to be closed; AppIds entries stay)",
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
