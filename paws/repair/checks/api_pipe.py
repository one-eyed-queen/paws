from __future__ import annotations

import stat

from ...sls import api as slsapi
from ..model import Problem


def check_api_pipe() -> list[Problem]:
    p = slsapi.API_PATH
    try:
        mode = p.lstat().st_mode
    except OSError:
        return []
    # SLSsteam's API is a plain file, not a pipe: src/api.cpp opens it with std::fstream and
    # watches it with inotify. a regular file is the normal, working state and must not be
    # flagged - only the wrong kind of thing at that path stops SLSsteam creating it
    if stat.S_ISREG(mode):
        return []

    def fix() -> str:
        p.unlink()
        return f"removed {p}"

    return [
        Problem(
            "api.pipe-not-a-pipe",
            f"{p} is a plain file",
            "SLSsteam's API needs a plain file at that path and cannot create one over a "
            "pipe, socket or directory: paws' commands would go nowhere",
            "delete it (SLSsteam recreates the file next start)",
            fix,
        )
    ]
