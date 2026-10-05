"""free stuff never goes in the config: steam hands it to everyone already, and faking ownership of a free game
(like CS2 in AdditionalApps) is exactly the kind of row that breaks downloads and loops steam"""

from __future__ import annotations

from .plan import GamePlan


def free_message(name: str, appid: str) -> str:
    if not name or name in (appid, f"app {appid}"):  # added by bare id: ask the store what it's called
        try:
            from ..sources.store import from_store

            name = from_store(appid).name
        except Exception:
            name = ""
    what = f"{name} ({appid})" if name else appid
    return f"{what} is free on steam, so paws doesn't add it. get it from the store, it's yours for free"


def strip_free(plan: GamePlan) -> tuple[bool, list[str]]:
    """(is the item itself free, the free extras taken out of the plan). the extras are dlc and linked apps"""
    from ..sources.store import free_ids

    free = free_ids([plan.appid, *plan.additional_apps])
    removed = [a for a in plan.additional_apps if a in free and a != plan.appid]
    plan.additional_apps = [a for a in plan.additional_apps if a not in free]
    return plan.appid in free, removed
