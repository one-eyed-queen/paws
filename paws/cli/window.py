from __future__ import annotations

import sys

from .. import launch


def open_window() -> int:
    result = launch.open_window()
    if not result.ok:
        print(f"paws: {result.explain()}", file=sys.stderr)
    return 0 if result.ok else 1
