from __future__ import annotations

from .. import config
from ..steam import depotcache as dcache
from ..steam import vdf
from ..util import undo
from .plan import GamePlan

LEGACY_SECTIONS = ("AdditionalDepots", "AdditionalPackages", "DecryptionKeys")

REMOVE_SECTIONS = (
    "AdditionalApps",
    "AppIds",
    "ManifestIds",
    "AppTokens",
    "FakeAppIds",
    "DepotBlacklist",
    *LEGACY_SECTIONS,
)


def _journaled(appid):
    manifests = []
    depots = []
    for record in undo.history(limit=500):
        d = record.get("detail", {})
        if d.get("appid") != appid:
            continue
        if record.get("kind") == "depotcache.add":
            manifests += [(int(dep), int(mid)) for dep, mid in d.get("files", [])]
        elif record.get("kind") == "vdf.add":
            depots += [str(x) for x in d.get("depots", [])]
    return manifests, sorted(set(depots))


def plan_remove(appid: str) -> GamePlan:
    plan = GamePlan(appid=str(appid))
    pars = config.parsed()

    def has(section: str) -> bool:
        v = pars.get(section)
        if isinstance(v, (dict, list)):
            return str(appid) in [str(x) for x in v]
        return False

    plan.notes += [f"{s}: {appid}" for s in REMOVE_SECTIONS if has(s)]
    manifests, depots = _journaled(plan.appid)
    plan.notes += [f"depotcache {d}_{m}" for d, m in manifests]
    plan.notes += [f"config.vdf depot {d}" for d in depots]
    return plan


def _name_for(appid: str) -> str:
    for _, line in config.refs_for(appid):
        name = line.partition("#")[2].strip()
        if name and name != appid:
            return name
    return ""


def list_added_games() -> list[dict]:
    """every game paws knows about: whatever's in AppIds/AdditionalApps, plus any base game that
    only has DLC entries (owned natively, never added itself - just a DLC added under it), so
    those DLCs are still reachable from the remove screen even though the base game isn't"""
    pars = config.parsed()
    dlc_data = {str(k): {str(d): n for d, n in (v or {}).items()} for k, v in (pars.get("DlcData") or {}).items()}
    ids = {str(x) for x in (pars.get("AppIds") or [])}
    ids |= {str(x) for x in (pars.get("AdditionalApps") or [])}
    ids |= set(dlc_data)
    return [
        {"appid": a, "name": _name_for(a), "dlc": dlc_data.get(a, {})}
        for a in sorted(ids, key=lambda x: int(x) if x.isdigit() else 0)
    ]


def remove_single_dlc(base_appid: str, dlc_id: str) -> dict:
    """remove just one DLC, leaving the base game (and its other DLCs) untouched"""
    removed = 0
    with config.batch():
        for section in REMOVE_SECTIONS:
            try:
                if config.remove_entry(section, dlc_id)[0]:
                    removed += 1
            except Exception:
                pass
        if config.remove_dlc_data(base_appid, dlc=dlc_id):
            removed += 1
    manifests, depots = _journaled(dlc_id)
    removed += sum(dcache.remove_manifest(dep, mid) for dep, mid in manifests)
    if depots:
        removed += len(vdf.remove_depot_keys(depots).get("removed", []))
    undo.log("apply_remove", {"appid": dlc_id, "removed": removed, "dlc_of": base_appid})
    return {"removed": removed}


def apply_remove(plan: GamePlan) -> dict:
    appid = plan.appid
    removed = 0
    with config.batch():
        for section in REMOVE_SECTIONS:
            try:
                if config.remove_entry(section, appid)[0]:
                    removed += 1
            except Exception:
                pass
        if "DlcData" in config.parsed() and config.remove_dlc_data(appid):
            removed += 1
        for record in undo.history(limit=500):
            if record.get("kind") != "config.add" or record["detail"].get("appid") != appid:
                continue
            for section, line in record["detail"].get("entries", []):
                try:
                    if config.remove_rendered(section, line)[0]:
                        removed += 1
                except Exception:
                    pass
    manifests, depots = _journaled(appid)
    removed += sum(dcache.remove_manifest(dep, mid) for dep, mid in manifests)
    if depots:
        removed += len(vdf.remove_depot_keys(depots).get("removed", []))
    undo.log("apply_remove", {"appid": appid, "removed": removed})
    return {"removed": removed}
