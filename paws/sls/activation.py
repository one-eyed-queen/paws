from __future__ import annotations

import threading
import time

from .. import steam
from ..config.entries import add_entry, render_item
from ..config.scalars import get_scalar
from ..config.seed import ensure_config
from ..config.where import find_config
from ..steam.find import find_steam
from ..steam.library import installed_games, library_paths
from .find import find_sls
from .tickets import Ticket, cache_dir, load_ticket_file, to_clipboard_text

DEFAULT_TIMEOUT = 25.0


def ensure_subscribed(appid: str) -> str | None:
    """steam only makes a ticket for an app it thinks you own, so the app goes in AdditionalApps for the run.
    returns the row when this call added it, so activate() can take it back out"""
    from ..config.scalars import get_list

    if find_config() is None:
        ensure_config()
    entry = render_item("AdditionalApps", {"id": appid, "name": f"activated {appid}"})
    if appid in get_list("AdditionalApps"):
        return None
    return entry if add_entry("AdditionalApps", entry)[0] else None


def _unsubscribe(entry: str | None, result: dict):
    """AdditionalApps overwrites the owner id: left in, it breaks downloads and can loop steam on loading user
    data. it only comes out with steam closed, a row removed while steam runs can get the game uninstalled"""
    if entry is None:
        return
    from ..config.entries import remove_rendered
    from ..config.io import batch

    if steam.is_running():
        result["note"] = "close steam, then run `paws fix` to take the activation row out of AdditionalApps"
        return
    with batch():
        remove_rendered("AdditionalApps", entry)


WANTS = ("encrypted", "normal", "both")
GRACE = 3.0  # for both how long to wait for the second file once the first turns up


def ticket_names(appid: str, want: str = "both") -> list[str]:
    enc, normal = f"encryptedTicket_{appid}.yaml", f"ticket_{appid}.yaml"
    return {"encrypted": [enc], "normal": [normal]}.get(want, [enc, normal])


def _found_for(cache, appid, want="both"):
    if not cache or not cache.exists():
        return []
    out = []
    for name in ticket_names(appid, want):
        p = cache / name
        if p.exists():
            t = load_ticket_file(p)
            if t:
                out.append(t)
    return out


def _kind(t):
    return "encrypted" if t.encrypted else "normal"


def _poll(cache, appid, timeout, found=None, want="both"):
    """wait for the wanted ticket files to show up.
    in both the encrypted one is the real deal, SLSsteam only saves it
    while the game itself is running and a lone ownership ticket just means the rights check passed"""
    if want not in WANTS:
        want = "both"
    found = list(found or [])
    required = {"encrypted", "normal"} if want != "both" else {"encrypted"}
    deadline = time.time() + timeout
    first = None
    while time.time() < deadline:
        for t in _found_for(cache, appid, want):
            if t.filename not in [x.filename for x in found]:
                found.append(t)
        have = {_kind(t) for t in found}
        if required <= have:
            break
        if have & required and first is None:
            first = time.time()
        if first is not None and time.time() - first >= GRACE:
            break
        time.sleep(1.0)
    return sorted(found, key=lambda t: not t.encrypted)


def mark_denuvo(appid: str, tickets: list[Ticket]) -> bool:
    """an encrypted ticket is what denuvo checks, so the game goes in DenuvoGames under the account that made it.
    SLSsteam then only unlocks it on that account and never on another one sharing this config"""
    from ..config.entries import add_map_list_item
    from ..config.io import batch

    enc = next((t for t in tickets if t.encrypted), None)
    if enc is None or not enc.steam_id.isdigit():
        return False
    name = installed_games().get(str(appid), str(appid))
    with batch():
        return add_map_list_item("DenuvoGames", {"steamid": enc.steam_id, "appid": appid, "name": name})[0]


def not_installed(appid: str) -> bool:
    """steam answers a launch of an uninstalled game with its install window, never the game itself"""
    return bool(library_paths()) and str(appid) not in installed_games()


def missing_tickets(appid: str, tickets: list[Ticket], want: str) -> list[str]:
    """the ones asked for that never turned up. for both only the encrypted one counts"""
    if want not in WANTS:
        want = "both"
    needed = {"encrypted": {"encrypted"}, "normal": {"normal"}, "both": {"encrypted"}}[want]
    have = {_kind(t) for t in tickets}
    return [ticket_names(appid, k)[0] for k in sorted(needed - have)]


def activate(
    appid: str,
    timeout: float = DEFAULT_TIMEOUT,
    copy_to_clipboard: bool = True,
    auto_manage: bool = True,
    steam_bin=None,
    sls_install=None,
    want: str = "both",
) -> dict:
    if want != "normal" and not_installed(appid):
        return {
            "method": None,
            "tickets": [],
            "copied": False,
            "want": want,
            "missing": ticket_names(appid, "encrypted"),
            "error": f"{appid} isn't installed. the encrypted ticket only gets made while the game is running, "
            "and launching an uninstalled game just opens steam's install window. install it first, "
            "or ask for the normal ticket only",
        }
    added = []
    try:
        result = _activate(appid, added, timeout, copy_to_clipboard, auto_manage, steam_bin, sls_install, want)
    except BaseException:
        if added:
            _unsubscribe(added[0], {})
        raise
    if added and added[0] and result.get("missing") and not result.get("error"):
        # the game still has to run once for the encrypted ticket, and that needs the row. `paws fix` tidies it later
        result["note"] = "the AdditionalApps row stays until that ticket lands, then run `paws fix` with steam closed"
    else:
        _unsubscribe(added[0] if added else None, result)
    if not result.get("error") and mark_denuvo(appid, result["tickets"]):
        result["denuvo"] = True
    return result


def _activate(appid, added, timeout, copy_to_clipboard, auto_manage, steam_bin, sls_install, want) -> dict:
    if want not in WANTS:
        want = "both"
    from ..util.clipboard import copy as cb_copy

    sls = sls_install or find_sls()
    st = steam_bin or find_steam()
    cache = cache_dir()
    result = {"method": None, "tickets": [], "copied": False, "error": None, "want": want, "missing": []}
    if not sls or not sls.config:
        result["error"] = "SLSsteam is not installed"
        return result
    if sls.kind == "windows":
        from ..windows.port import UNDER_CONSTRUCTION

        result["error"] = UNDER_CONSTRUCTION
        return result

    added.append(ensure_subscribed(appid))

    # no `install|appid|0` through the API: that queued a real download and is why steam jumped to install
    api_on = get_scalar("API") == "yes"
    if api_on and steam.is_running():
        result["method"] = "api"
        steam.run_game_id(appid, st, sls, wait=3.0)
        found = _poll(cache, appid, timeout=timeout, want=want)
        result["tickets"] = found
        result["missing"] = missing_tickets(appid, found, want)
        if found and copy_to_clipboard:
            result["copied"] = any(cb_copy(to_clipboard_text(t)) for t in found)
        return result

    if not auto_manage:
        result["error"] = "ticket not generated (SLS API unavailable)"
        return result

    if steam.is_running() and steam.sls_injected():
        result["method"] = "probe"
        probe_error = {}

        def _probe():
            try:
                steam.probe_running(appid, st, sls, timeout=timeout)
            except steam.SteamError as e:
                probe_error["error"] = str(e)

        runner = threading.Thread(target=_probe, daemon=True)
        runner.start()
        found = _poll(cache, appid, timeout=timeout, want=want)
        runner.join()
        if probe_error.get("error") and not found:
            result["error"] = probe_error["error"]
        result["tickets"] = found
        result["missing"] = missing_tickets(appid, found, want)
        if found and copy_to_clipboard:
            result["copied"] = any(cb_copy(to_clipboard_text(t)) for t in found)
        return result

    result["method"] = "oneshot"
    inject_error = {}

    def _inject():
        try:
            steam.one_shot_inject(st, sls, f"steam://rungameid/{appid}", timeout=timeout)
        except steam.SteamError as e:
            inject_error["error"] = str(e)

    run = threading.Thread(target=_inject, daemon=True)
    run.start()
    found = _poll(cache, appid, timeout=timeout, want=want)
    run.join()
    if "error" in inject_error:
        result["error"] = inject_error["error"]
        return result
    result["tickets"] = found
    result["missing"] = missing_tickets(appid, found, want)
    if found and copy_to_clipboard:
        result["copied"] = any(cb_copy(to_clipboard_text(t)) for t in found)
    return result
