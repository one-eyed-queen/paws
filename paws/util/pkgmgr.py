from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

SYSTEM = ("rpm-ostree", "pacman", "apt", "dnf", "zypper", "xbps", "apk", "emerge")
AUR_HELPERS = ("paru", "yay")
SANDBOXED = ("flatpak", "snap")
ALL = (*SYSTEM, *AUR_HELPERS, *SANDBOXED)

PROGRAM = {"xbps": "xbps-install"}


def _has(manager):
    return bool(shutil.which(PROGRAM.get(manager, manager)))


INSTALL: dict[str, dict[str, str]] = {
    "steam": {
        "pacman": "sudo pacman -S steam",
        "apt": "sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install steam-installer",
        "dnf": "sudo dnf install steam",
        "zypper": "sudo zypper install steam",
        "xbps": "sudo xbps-install -S void-repo-nonfree void-repo-multilib void-repo-multilib-nonfree && sudo xbps-install -S steam",
        "emerge": "sudo emerge --ask games-util/steam-launcher",
        "flatpak": "flatpak install flathub com.valvesoftware.Steam",
        "snap": "sudo snap install steam",
    },
    "git": {
        "pacman": "sudo pacman -S git",
        "apt": "sudo apt install git",
        "dnf": "sudo dnf install git",
        "zypper": "sudo zypper install git",
        "xbps": "sudo xbps-install -S git",
        "apk": "sudo apk add git",
        "emerge": "sudo emerge --ask dev-vcs/git",
        "rpm-ostree": "sudo rpm-ostree install git",
    },
    "wl-clipboard": {
        "pacman": "sudo pacman -S wl-clipboard",
        "apt": "sudo apt install wl-clipboard",
        "dnf": "sudo dnf install wl-clipboard",
        "zypper": "sudo zypper install wl-clipboard",
        "xbps": "sudo xbps-install -S wl-clipboard",
        "apk": "sudo apk add wl-clipboard",
        "emerge": "sudo emerge --ask gui-apps/wl-clipboard",
        "rpm-ostree": "sudo rpm-ostree install wl-clipboard",
    },
    "xclip": {
        "pacman": "sudo pacman -S xclip",
        "apt": "sudo apt install xclip",
        "dnf": "sudo dnf install xclip",
        "zypper": "sudo zypper install xclip",
        "xbps": "sudo xbps-install -S xclip",
        "apk": "sudo apk add xclip",
        "emerge": "sudo emerge --ask x11-misc/xclip",
        "rpm-ostree": "sudo rpm-ostree install xclip",
    },
    "slssteam": {
        "paru": "paru -S slssteam",
        "yay": "yay -S slssteam",
    },
}

UPDATE: dict[str, str] = {
    "pacman": "sudo pacman -Syu {pkg}",
    "apt": "sudo apt update && sudo apt install --only-upgrade {pkg}",
    "dnf": "sudo dnf upgrade {pkg}",
    "zypper": "sudo zypper update {pkg}",
    "xbps": "sudo xbps-install -Su {pkg}",
    "apk": "sudo apk add -u {pkg}",
    "emerge": "sudo emerge --ask --update {pkg}",
    "rpm-ostree": "rpm-ostree upgrade",
}

REMOVE: dict[str, str] = {
    "pacman": "sudo pacman -R {pkg}",
    "apt": "sudo apt remove {pkg}",
    "dnf": "sudo dnf remove {pkg}",
    "zypper": "sudo zypper remove {pkg}",
    "xbps": "sudo xbps-remove {pkg}",
    "apk": "sudo apk del {pkg}",
    "emerge": "sudo emerge --ask --depclean {pkg}",
    "rpm-ostree": "sudo rpm-ostree uninstall {pkg}",
}


def available() -> list[str]:
    return [m for m in ALL if _has(m)]


def system_manager() -> str | None:
    return next((m for m in SYSTEM if _has(m)), None)


def aur_helper() -> str | None:
    return next((m for m in AUR_HELPERS if shutil.which(m)), None)


@dataclass
class Owner:
    manager: str
    package: str
    version: str

    def __str__(self) -> str:
        return f"{self.package} {self.version}".strip()


def _run(command):
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def owner_of(path) -> Owner | None:
    manager = system_manager()
    p = str(path)
    if manager == "pacman":
        parts = (_run(["pacman", "-Qo", p]) or "").split()
        return Owner("pacman", parts[-2], parts[-1]) if len(parts) >= 2 else None
    if manager == "apt":
        out = _run(["dpkg", "-S", p])
        if not out:
            return None
        pkg = out.split(":", 1)[0].strip()
        version = (_run(["dpkg-query", "-W", "-f=${Version}", pkg]) or "").strip()
        return Owner("apt", pkg, version)
    if manager == "apk":
        out = _run(["apk", "info", "-W", p]) or ""
        word = out.strip().split()[-1] if "owned by" in out else ""
        if not word:
            return None
        name, _, rest = word.rpartition("-r")
        base, _, version = name.rpartition("-")
        return Owner("apk", base or word, f"{version}-r{rest}" if version else "")
    if manager in ("dnf", "zypper", "rpm-ostree"):
        parts = (_run(["rpm", "-qf", "--qf", "%{NAME} %{VERSION}-%{RELEASE}", p]) or "").split()
        return Owner(manager, parts[0], parts[1]) if len(parts) >= 2 else None
    return None


def install_hints(thing: str) -> list[str]:
    have = set(available())
    return [command for manager, command in INSTALL.get(thing, {}).items() if manager in have]


def update_hint(pkg: str, manager: str | None) -> str:
    if manager == "pacman":
        helper = aur_helper()
        return f"{helper} -S {pkg}" if helper else UPDATE["pacman"].format(pkg=pkg)
    template = UPDATE.get(manager or "")
    return template.format(pkg=pkg) if template else "your package manager"


def remove_hint(pkg: str, manager: str | None) -> str:
    template = REMOVE.get(manager or "")
    return template.format(pkg=pkg) if template else "your package manager"
