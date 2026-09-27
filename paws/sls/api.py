from __future__ import annotations

import os
from pathlib import Path

API_PATH = Path(os.environ.get("PAWS_SLS_API") or "/tmp/SLSsteam.API")


def write_api_command(command: str, path: Path | None = None) -> bool:
    p = path or API_PATH
    try:
        if not p.exists():
            return False
        with p.open("w") as f:
            f.write(command.strip("\n") + "\n")
        return True
    except OSError:
        return False
