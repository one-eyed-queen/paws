from __future__ import annotations

import os
import shutil

from ..paths import HOME
from ..util import pkgmgr
from .errors import SlsError
from .model import SlsInstall


def paws_owns(lib_dir):
    if (lib_dir / "paws.info.json").exists():
        return True
    return lib_dir in (
        HOME / ".local/share/SLSsteam",
        HOME / ".var/app/com.valvesoftware.Steam/.local/share/SLSsteam",
    )


def uninstall(sls: SlsInstall | None) -> bool:
    if sls is None:
        return False
    if sls.kind == "windows":
        from ..windows import port

        port.unsupported()
    if sls.managed_by:
        raise SlsError(
            f"SLSsteam here is owned by {sls.managed_by} ({sls.lib_dir}); paws won't touch package files. "
            f"remove it with: {pkgmgr.remove_hint('slssteam', sls.managed_by)}"
        )
    if sls.lib_dir:
        if not paws_owns(sls.lib_dir):
            raise SlsError(f"{sls.lib_dir} wasn't installed by paws, so paws won't delete it. remove it by hand.")
        shutil.rmtree(sls.lib_dir)
    for name in ("steam.desktop", "steam-native.desktop"):
        apps = HOME / ".local/share/applications" / name
        if apps.exists():
            try:
                text = apps.read_text()
            except OSError:
                continue
            if "LD_AUDIT" in text and "SLSsteam" in text:
                os.remove(apps)
    return True
