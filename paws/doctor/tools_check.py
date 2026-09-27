from __future__ import annotations

import shutil

from ..util import pkgmgr
from .result import CheckResult


def tools_checks() -> list:
    if shutil.which("git"):
        return []
    hints = pkgmgr.install_hints("git")
    how = hints[0] if hints else "install git with your package manager"
    return [CheckResult(False, "git missing", f"paws can't update itself without it: {how}", "warn")]
