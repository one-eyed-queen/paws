from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .. import config
from ..textdrop import Parsed, clean_name
from .apply import apply_plan
from .plan import GamePlan
from .remove import apply_remove, plan_remove


def lookup_names(ids: list[str], workers: int = 5) -> dict[str, str]:
    from ..sources.store import from_store

    def one(appid: str) -> tuple[str, str]:
        try:
            return appid, clean_name(from_store(appid).name)
        except Exception:
            return appid, ""

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {a: n for a, n in pool.map(one, ids) if n}


def plans_from(parsed: Parsed, names: dict[str, str] | None = None) -> list[GamePlan]:
    names = names or {}
    label = lambda i: clean_name(i.name) or names.get(i.id, "") or f"app {i.id}"  # noqa: E731
    if parsed.kind == "dlc" and parsed.base_id:
        base = parsed.base_name or names.get(parsed.base_id, "") or f"app {parsed.base_id}"
        plan = GamePlan(appid=parsed.base_id, name=base)
        plan.names[parsed.base_id] = base
        plan.additional_apps = [parsed.base_id]
        for it in parsed.items:
            plan.additional_apps.append(it.id)
            plan.names[it.id] = f"{label(it)} (DLC of {base})"
            plan.dlc_data[it.id] = label(it)
        return [plan]
    plans = []
    for it in parsed.items:
        name = label(it)
        if it.note:
            name = f"{name} ({it.note})"
        plan = GamePlan(appid=it.id, name=name)
        plan.additional_apps = [it.id]
        plans.append(plan)
    return plans


def apply_bulk(plans: list[GamePlan]) -> dict:
    from ..sources.store import free_ids

    free_ids([a for p in plans for a in (p.appid, *p.additional_apps)])  # one store round trip, apply_plan reuses it
    already = sum(1 for p in plans if config.refs_for(p.appid))
    applied, added, errors = 0, 0, []
    with config.batch():
        for p in plans:
            result = apply_plan(p)
            applied += result["applied"]
            added += result.get("added", 0)
            errors += result["errors"]
    return {"games": len(plans), "already_there": already, "applied": applied, "added": added, "errors": errors}


def remove_bulk(ids: list[str]) -> dict:
    removed_games, removed = 0, 0
    with config.batch():
        for appid in ids:
            n = apply_remove(plan_remove(appid))["removed"]
            removed += n
            removed_games += 1 if n else 0
    return {
        "games": len(ids),
        "removed_games": removed_games,
        "removed": removed,
        "not_found": len(ids) - removed_games,
    }
