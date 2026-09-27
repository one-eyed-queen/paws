from __future__ import annotations


from .. import config
from ..steam import depotcache as dcache
from ..steam import vdf
from ..util import undo
from .plan import GamePlan


def apply_plan(plan: GamePlan, *, checked: set[str] | None = None) -> dict:
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
                        vdf_keys[depot] = plan.decryption_keys[depot]
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
    return {"applied": applied, "errors": errors, "added": len(added)}


def _apply_cfg(plan, c):
    kind, _, rest = c.detail.partition(" ")
    value = rest.split()[0]
    name = plan.names.get(value.partition(":")[0]) or plan.name or value
    out = []

    def put(section: str, line: str):
        if config.add_entry(section, line)[0]:  # a skipped duplicate isn't ours to undo
            out.append((section, line))

    if kind == "AdditionalApps":
        put("AdditionalApps", config.render_item("AdditionalApps", id=value, name=name))
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
