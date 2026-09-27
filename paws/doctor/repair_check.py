from __future__ import annotations

from .result import CheckResult


def repair_checks() -> list:
    from .. import repair

    try:
        problems = repair.scan()
    except Exception:
        return []
    if not problems:
        return [CheckResult(True, "Repairs", "nothing is broken", "ok")]
    fixable = sum(p.fixable for p in problems)
    head = "; ".join(p.title for p in problems[:3]) + ("..." if len(problems) > 3 else "")
    sev = "error" if any(p.severity == "error" for p in problems) else "warn"
    return [
        CheckResult(False, "Repairs", f"{len(problems)} problem(s), {fixable} fixable ({head}). run `paws fix`", sev)
    ]
