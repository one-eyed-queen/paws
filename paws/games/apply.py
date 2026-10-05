from __future__ import annotations


from .. import config
from ..steam import depotcache as dcache
from ..steam import vdf
from ..util import undo
from .free import free_message, strip_free
from .plan import GamePlan


def apply_plan(plan: GamePlan, *, checked: set[str] | None = None) -> dict:
    item_is_free, _extras = strip_free(plan)  # every way in (screen, drop, bulk, cli) ends up here
    if item_is_free:
        return {
            "applied": 0,
            "errors": [free_message(plan.name, plan.appid)],
            "added": 0,
            "nudged": False,
            "free": True,
        }
    applied = 0
    errors = []
    added = []
    vdf_keys = {}
    manifests = []
    with config.batch():
        for c in plan.changes():
            if checked is not None and c.key not in checked:
                continue
            try:
                if c.target == "config.yaml":
                    added.extend(_apply_cfg(plan, c))
                elif c.target == "config.vdf":
                    depot = c.detail.split()[-1]
                    if depot in plan.decryption_keys:
                        key = plan.decryption_keys[depot]
                        vdf_keys[depot] = key
                        name = plan.names.get(depot) or plan.name or plan.appid
                        # also written to SLSsteam's own DecryptionKeys section, not just
                        # config.vdf: a private build can use it to resolve the current
                        # manifest for a depot itself, instead of needing a pinned ManifestIds
                        # value that goes stale the moment the depot updates
                        key_line = config.render_item("DecryptionKeys", id=depot, key=key, name=name)
                        if config.add_entry("DecryptionKeys", key_line)[0]:
                            added.append(("DecryptionKeys", key_line))
                elif c.target == "depotcache":
                    manifests.extend(m for m in plan.manifest_files if f"manifest_{m[0]}_{m[1]}" == c.detail)
                applied += 1
            except Exception as e:
                errors.append(f"{c.detail}: {e}")
    if vdf_keys:
        fresh = sorted(set(vdf_keys) - vdf.existing_depot_ids(list(vdf_keys)))
        result = vdf.inject_depot_keys(vdf_keys)
        if result.get("error"):
            errors.append(f"config.vdf: {result['error']}")
            applied -= len(vdf_keys)
        elif fresh:
            undo.log("vdf.add", {"appid": plan.appid, "depots": fresh})
    if manifests:
        try:
            copied = dcache.install_manifests(manifests)
            if copied:
                undo.log("depotcache.add", {"appid": plan.appid, "files": [list(x) for x in copied]})
        except Exception as e:
            errors.append(f"depotcache: {e}")
            applied -= len(manifests)
    if added:
        undo.log("config.add", {"appid": plan.appid, "entries": added})
    undo.log("apply_plan", {"appid": plan.appid, "applied": applied, "errors": errors})
    nudged = bool(applied) and _nudge_steam(plan.appid)
    return {"applied": applied, "errors": errors, "added": len(added), "nudged": nudged}


def _nudge_steam(appid: str) -> bool:
    """if steam is already running with the API pipe on, ask it to install the app right away
    instead of waiting on a mechanism that may never fire for it.

    SLSsteam only asks Valve for an app's depot/product info when it sees the app get ADDED
    while it's already running (config.cpp's CConfig::setAdditionalApps skips that diff entirely
    on firstLoad). an app that's already in AdditionalApps by the time steam starts never gets
    that request and just sits at 0B forever. the API pipe's install command goes through
    steam's own native IClientAppManager::installApp - same as the user clicking Install
    themselves, and unlike steam://rungameid it doesn't try to RUN anything, so there's no
    "missing executable" failure when nothing's downloaded yet.
    """
    if not appid or not appid.isdigit():
        return False
    try:
        from ..config.scalars import get_scalar
        from ..sls.api import write_api_command
        from ..steam import is_running

        if not is_running() or get_scalar("API") != "yes":
            return False
        return write_api_command(f"install|{appid}|0")
    except Exception:
        return False


def _apply_cfg(plan, c):
    kind, _, rest = c.detail.partition(" ")
    value = rest.split()[0]
    name = plan.names.get(value.partition(":")[0]) or plan.name or value
    out = []

    def put(section: str, line: str):
        if config.add_entry(section, line)[0]:  # a skipped duplicate isn't ours to undo
            out.append((section, line))

    if kind == "AppIds":
        put("AppIds", config.render_item("AppIds", id=value, name=name))
        # AppIds is a blacklist by default - without this, adding a game here would tell
        # SLSsteam to EXCLUDE it, the opposite of what adding a game means
        config.set_scalar("UseWhitelist", "yes")
    elif kind == "AdditionalPackages":
        put("AdditionalPackages", config.render_item("AdditionalPackages", id=value, name=name))
    elif kind == "ManifestIds":
        depot, _, manifest = value.partition(":")
        put("ManifestIds", config.render_item("ManifestIds", depot=depot, manifest=manifest, name=name))
    elif kind == "AppTokens":
        app = value.partition(":")[0]  # the row is id:token the token lives in plan.tokens
        put("AppTokens", config.render_item("AppTokens", id=app, token=plan.tokens[app], name=name))
    elif kind == "DlcData":
        dlc, _, rest = value.partition("(")
        dlc = dlc.strip()
        dname = rest.rstrip(")").strip() if rest else plan.dlc_data.get(dlc, "")
        if config.add_dlc_data(plan.appid, dlc, dname)[0]:
            out.append(("DlcData", f'    {dlc}: "{dname}"'))
    return out
