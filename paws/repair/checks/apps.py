"""AdditionalApps is how SLSsteam injects an app you don't own into your library: it appends the
list to the apps steam thinks you're subscribed to, and that is the only way an unowned game ever
shows up. so those rows are load-bearing and must stay.

what breaks is the same row for an app steam already lists for you: AdditionalApps overrides that
app's owner id, downloads fail and steam can loop on "loading user data". that is the only kind of
row this check takes out, and only with steam closed (removing one live can make steam uninstall
the game, because SLSsteam reports its license as changed)"""

from __future__ import annotations

import re
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
            from ...games.plan import unlocked_by_paws
            from ...steam.library import owned_appids

            owned = owned_appids() - unlocked_by_paws()  # installed because paws unlocked it isn't owned
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
    from ...games.download import blocked_rows, packages_supported, reads, unblock

    text = safe_read(config_path)
    rows = blocked_rows(text) if text is not None and packages_supported() else []
    if not rows:
        return []
    where = "AdditionalPackageApps" if reads("AdditionalPackageApps") else "their store package"

    def fix() -> str:
        from ...steam import is_running

        if is_running():
            return "close steam first: taking these out while it runs can make it uninstall the games. nothing changed"
        moved = unblock(config_path)
        if not moved:
            return "couldn't reach the store for their packages, nothing changed. try again online"
        return f"moved {len(moved)} game(s) to {where}: {', '.join(moved)}. backup kept"

    listed = ", ".join(name or appid for _i, appid, name in rows[:6])
    return [
        Problem(
            "config.downloads-blocked",
            f"{len(rows)} game(s) can't download (0 B in steam)",
            f"{listed}. their AdditionalApps row overrides the owner, and with DisableUpdates it hides the download",
            f"move each to {where} and take the AdditionalApps row out (steam has to be closed)",
            fix,
            "error",
        )
    ]


def check_public_build(config_path: Path) -> list[Problem]:
    """public SLSsteam puts games in the library but can't download them: tell the user instead of a silent 0 B"""
    from ...games.download import ACTIVATION_NOTE, known_build, packages_supported

    if not known_build() or packages_supported():
        return []
    from ...config.lines import _code_part, block_end_line, item_key, section_index
    from ...config.tidy import split_comment

    lines = (safe_read(config_path) or "").splitlines()
    index = section_index(lines, "AdditionalApps")
    if index is None:
        return []
    names = [split_comment(l)[1] or str(item_key(l)) for l in lines[index + 1 : block_end_line(lines, index)]
             if _code_part(l).strip() and not split_comment(l)[1].startswith(ACTIVATION_NOTE)]
    if not names:
        return []
    return [
        Problem(
            "sls.public-no-downloads",
            f"{len(names)} game(s) show in steam but can't download (0 B)",
            f"{', '.join(names[:6])}. the installed SLSsteam is the public build: it adds games to the library but "
            "doesn't download them, so steam shows 0 B. that's the build, not your config - nothing here is broken",
            "this isn't a config error paws can fix; 0 B is expected on the public build",
            None,
            "info",
        )
    ]


def check_disable_updates_0b(config_path: Path) -> list[Problem]:
    """DisableUpdates: yes with AdditionalApps rows hides update info for those games, so they sit at 0 B.
    only on a build that can download (on public 0 B is the build), and only for rows check_downloads_blocked
    doesn't already move to a store package"""
    import yaml

    from ...config.tidy import split_comment
    from ...games.download import ACTIVATION_NOTE, blocked_rows, packages_supported

    text = safe_read(config_path)
    if not text or not packages_supported():
        return []
    try:
        data = yaml.safe_load(text) or {}
    except Exception:
        return []
    if not isinstance(data, dict) or data.get("DisableUpdates") is not True:
        return []
    lines = text.splitlines()
    idx = section_index(lines, "AdditionalApps")
    if idx is None:
        return []
    covered = {i for i, _appid, _name in blocked_rows(text)}
    apps = [
        split_comment(lines[i])[1] or str(item_key(lines[i]))
        for i in range(idx + 1, block_end_line(lines, idx))
        if i not in covered and _code_part(lines[i]).strip() and not split_comment(lines[i])[1].startswith(ACTIVATION_NOTE)
    ]
    if not apps:
        return []

    def fix() -> str:
        import re

        cur = safe_read(config_path) or ""
        updated = re.sub(r"(?mi)^(DisableUpdates:\s*)(?:yes|true|on)\b", r"\g<1>no", cur)
        if updated == cur:
            return "DisableUpdates is already off, nothing changed"
        backup.backup_file(config_path)
        write_now(config_path, updated)
        return "DisableUpdates is off now, so steam fetches update info for these games again; backup kept"

    return [
        Problem(
            "config.disable-updates-0b",
            f"{len(apps)} game(s) at 0 B because DisableUpdates is on",
            f"{', '.join(apps[:6])}. with DisableUpdates on, SLSsteam hides steam's update info for AdditionalApps "
            "games, so steam has nothing to download",
            "turn DisableUpdates off (steam will update your other games again too)",
            fix,
            "warn",
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
        result = restore(restart_steam=True)
        if result.get("error") == "steam didn't close":
            return "steam didn't close, so nothing changed. quit it from its own menu and run the fix again"
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
            "close steam, put them back into its config.vdf and depotcache, start steam again",
            fix,
            "error",
        )
    ]


DENIED = re.compile(
    r"BYldRequestDepotManifest\(App: (\d+), Depot: (\d+), Manifest: (\d+)[^)]*\): Failed to get manifest request code, '([^']*)'"
)


def denied_manifests(log_text: str) -> dict[str, tuple[str, str, str]]:
    """depot -> (app, manifest, valve's answer) for manifest codes steam's latest session couldn't get"""
    session = log_text.rsplit("Client version:", 1)[-1]
    return {depot: (app, manifest, why) for app, depot, manifest, why in DENIED.findall(session)}


def check_manifest_code_denied(config_path: Path) -> list[Problem]:
    """steam's "no internet connection" on a download: valve refused the depot's manifest request code"""
    from ...games.download import known_build, packages_supported
    from ...steam.find import find_steam

    steam = find_steam()
    if not steam or not steam.root:
        return []
    log = safe_read(Path(steam.root) / "logs" / "content_log.txt") or ""
    cache = Path(steam.depotcache) if steam.depotcache else None
    denied = {
        d: v for d, v in denied_manifests(log).items() if not (cache and (cache / f"{d}_{v[1]}.manifest").is_file())
    }
    if not denied:
        return []
    listed = ", ".join(f"depot {d} of app {app} ({why})" for d, (app, _m, why) in list(denied.items())[:4])
    if known_build() and not packages_supported():
        why, todo = (
            "the installed SLSsteam is the public build, which can't get these codes (private builds fetch them)",
            "drop a private SLSsteam build's .7z on paws, or that depot's .manifest file",
        )
    else:
        why, todo = (
            "SLSsteam didn't get the code from its manifest service either",
            "start steam through paws so SLSsteam is loaded and try again, or drop that depot's .manifest file",
        )
    return [
        Problem(
            "steam.manifest-code-denied",
            f"steam said \"no internet connection\" for {len(denied)} depot(s): valve refused their manifest code",
            f"{listed}. your connection is fine: valve only gives that code for games you own. {why}",
            todo,
            None,
            "warn",
        )
    ]
