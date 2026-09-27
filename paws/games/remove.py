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
