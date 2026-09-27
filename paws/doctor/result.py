from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckResult:
    ok: bool
    label: str
    detail: str = ""
    severity: str = "info"
