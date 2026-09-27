from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Problem:
    id: str
    title: str
    detail: str
    fix_note: str = ""
    fix: Callable[[], str] | None = None
    severity: str = "warn"

    @property
    def fixable(self) -> bool:
        return self.fix is not None
