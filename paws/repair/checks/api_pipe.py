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
    if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
        return []

    def fix() -> str:
        p.unlink()
        return f"removed {p}"

    return [
        Problem(
            "api.pipe-not-a-pipe",
            f"{p} is a plain file",
            "something wrote to it before SLSsteam made the pipe, so SLSsteam can't create it: paws' commands go nowhere",
            "delete it (SLSsteam recreates the pipe next start)",
            fix,
        )
    ]
