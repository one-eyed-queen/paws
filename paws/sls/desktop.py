from __future__ import annotations

import subprocess
from pathlib import Path

from ..paths import HOME

_LAUNCHERS = {
    "steam.desktop": "Exec=steam %U",
    "steam-native.desktop": "Exec=steam-native %U",
}


def write_launcher(sls_dir):
    apps = HOME / ".local/share/applications"
    apps.mkdir(parents=True, exist_ok=True)
    audit = f'LD_AUDIT="{sls_dir}/library-inject.so:{sls_dir}/SLSsteam.so"'
    wrote = False
    for name, fallback in _LAUNCHERS.items():
        sys_desktop = Path("/usr/share/applications") / name
        if not sys_desktop.exists():
            if name != "steam.desktop":
                continue
            content = f"[Desktop Entry]\nName=Steam\nComment=SLSsteam (paws)\n{fallback}\nIcon=steam\nTerminal=false\nType=Application\nCategories=Game;\nMimeType=x-scheme-handler/steam;\n"
        else:
            content = sys_desktop.read_text()
            if "Exec=" not in content:
                continue
        lines = []
        for line in content.splitlines():
            if line.startswith("Exec=") and "LD_AUDIT" not in line:
                line = f"Exec=env {audit} {line[len('Exec=') :]}"
            lines.append(line)
        (apps / name).write_text("\n".join(lines) + "\n")
        wrote = True
    if wrote:
        try:
            subprocess.run(["update-desktop-database", str(apps)], capture_output=True)
        except Exception:
            pass
