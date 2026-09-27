from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .launch.argv import CLASS
from .paths import DATA_DIR

ICON_SRC = DATA_DIR / "img" / "paws-icon.png"
SIZES = (16, 24, 32, 48, 64, 96, 128, 256, 512)


def share_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def _icon_value():
    big = icon_file(256)
    return str(big) if big.exists() else "paws"


def desktop_file() -> Path:
    return share_dir() / "applications" / "paws.desktop"


def icon_file(size: int) -> Path:
    return share_dir() / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "paws.png"


def _exec_path():
    on_path = shutil.which("paws")
    local = Path.home() / ".local/bin/paws"
    if on_path:
        return on_path
    return str(local) if local.exists() else f"{sys.executable} -m paws"


def entry_text(exec_path: str | None = None, icon: str | None = None) -> str:
    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=paws\n"
        "GenericName=SLSsteam Manager\n"
        "Comment=Menu-driven SLSsteam manager for Linux\n"
        f"Exec={exec_path or _exec_path()} --window\n"
        "Terminal=false\n"
        f"Icon={icon or _icon_value()}\n"
        f"StartupWMClass={CLASS}\n"
        "Categories=Utility;\n"
        "Keywords=paws;sls;steam;\n"
    )


def desktop_dir() -> Path:
    conf = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
    try:
        for line in conf.read_text().splitlines():
            if line.startswith("XDG_DESKTOP_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"')
                return Path(raw.replace("$HOME", str(Path.home())))
    except OSError:
        pass
    return Path.home() / "Desktop"


def shortcut_file() -> Path:
    return desktop_dir() / "paws.desktop"


def has_shortcut() -> bool:
    return shortcut_file().exists()


def has_entry() -> bool:
    return desktop_file().exists()


def add_shortcut() -> Result:
    if not icon_file(256).exists():
        result = install()
        if not result.ok:
            return result
    f = shortcut_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(entry_text())
        f.chmod(0o755)
    except OSError as error:
        return Result(False, [], f"couldn't write {f}: {error}")
    if shutil.which("gio"):
        try:
            subprocess.run(
                ["gio", "set", str(f), "metadata::trusted", "true"],
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return Result(True, [f], "added the paws shortcut to your desktop")


def remove_shortcut() -> Result:
    f = shortcut_file()
    try:
        f.unlink(missing_ok=True)
    except OSError as error:
        return Result(False, [], f"couldn't remove {f}: {error}")
    return Result(True, [f], "removed the paws shortcut from your desktop")


@dataclass
class Result:
    ok: bool
    files: list[Path]
    note: str = ""


def install() -> Result:
    if not ICON_SRC.exists():
        return Result(False, [], f"icon not found: {ICON_SRC}")
    written = []
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is None:
        destination = icon_file(256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ICON_SRC, destination)
        written.append(destination)
    else:
        src = Image.open(ICON_SRC).convert("RGBA")
        for n in SIZES:
            destination = icon_file(n)
            destination.parent.mkdir(parents=True, exist_ok=True)
            src.resize((n, n), Image.LANCZOS).save(destination, optimize=True)
            written.append(destination)
    d = desktop_file()
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(entry_text())
    written.append(d)
    _refresh_caches()
    return Result(True, written, f"installed the paws icon ({len(written) - 1} size(s)) and launcher")


def uninstall() -> Result:
    gone = []
    for p in [desktop_file(), *(icon_file(n) for n in SIZES)]:
        if p.exists():
            p.unlink()
            gone.append(p)
    _refresh_caches()
    return Result(True, gone, f"removed {len(gone)} file(s)")


def _refresh_caches():
    theme = share_dir() / "icons" / "hicolor"
    for command in (
        ["gtk-update-icon-cache", "-q", "-t", "-f", str(theme)],
        ["update-desktop-database", "-q", str(desktop_file().parent)],
    ):
        if shutil.which(command[0]):
            try:
                subprocess.run(command, capture_output=True, timeout=15, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
    desktops = (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper()
    if "KDE" in desktops:
        for tool in ("kbuildsycoca6", "kbuildsycoca5"):
            if shutil.which(tool):
                try:
                    subprocess.Popen(
                        [tool, "--noincremental"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except OSError:
                    pass
                break
    if shutil.which("xdg-desktop-menu"):
        try:
            subprocess.run(
                ["xdg-desktop-menu", "forceupdate"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
