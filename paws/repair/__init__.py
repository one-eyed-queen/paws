from __future__ import annotations

from .checks import refresh_known_good, scan
from .model import Problem
from .reset import clear_tickets, reset_config


def apply(problem: Problem) -> tuple[bool, str]:
    if problem.fix is None:
        return False, "no automatic fix for this one"
    try:
        return True, problem.fix()
    except Exception as error:
        return False, f"couldn't fix it: {error}"


def apply_all(problems: list[Problem]) -> list[tuple[Problem, bool, str]]:
    return [(p, *apply(p)) for p in problems if p.fixable]


__all__ = ["clear_tickets", "reset_config", "Problem", "scan", "refresh_known_good", "apply", "apply_all"]
