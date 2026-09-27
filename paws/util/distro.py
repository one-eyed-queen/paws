from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

OS_RELEASE_FILES = ("/etc/os-release", "/usr/lib/os-release")

FAMILIES = {
    "arch": "arch",
    "archlinux": "arch",
    "debian": "debian",
    "ubuntu": "debian",
    "fedora": "fedora",
    "rhel": "fedora",
    "centos": "fedora",
    "opensuse": "suse",
    "suse": "suse",
    "sles": "suse",
    "void": "void",
    "alpine": "alpine",
    "gentoo": "gentoo",
    "nixos": "nix",
}

IMMUTABLE_IDS = {
    "steamos": "SteamOS keeps / read-only (unlock with `sudo steamos-readonly disable`). paws only writes to your home, so it doesn't need that.",
    "bazzite": "Bazzite is image based: system packages go through rpm-ostree. paws only writes to your home.",
    "silverblue": "Silverblue is image based: system packages go through rpm-ostree. paws only writes to your home.",
    "kinoite": "Kinoite is image based: system packages go through rpm-ostree. paws only writes to your home.",
    "aurora": "Aurora is image based: system packages go through rpm-ostree. paws only writes to your home.",
    "bluefin": "Bluefin is image based: system packages go through rpm-ostree. paws only writes to your home.",
    "nixos": "NixOS is declarative: install Steam with `programs.steam.enable = true;`. paws only writes to your home.",
}


@dataclass
class Distro:
    id: str = "unknown"
    like: list[str] = field(default_factory=list)
    name: str = "Linux"
    variant_id: str = ""
    family: str = "other"
    immutable_note: str = ""

    @property
    def immutable(self) -> bool:
        return bool(self.immutable_note)


def parse_os_release(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        try:
            parts = shlex.split(value)
            out[key.strip()] = parts[0] if parts else ""
        except ValueError:
            out[key.strip()] = value.strip().strip("\"'")
    return out


def family_of(distro_id: str, like: list[str]) -> str:
    for candidate in (distro_id, *like):
        fam = FAMILIES.get(candidate.lower())
        if fam:
            return fam
    return "other"


def from_text(text: str, ostree_booted: bool = False) -> Distro:
    data = parse_os_release(text)
    did = data.get("ID", "unknown").lower()
    like = [x.lower() for x in data.get("ID_LIKE", "").split()]
    d = Distro(
        id=did,
        like=like,
        name=data.get("PRETTY_NAME") or data.get("NAME") or did,
        variant_id=data.get("VARIANT_ID", "").lower(),
        family=family_of(did, like),
    )
    note = IMMUTABLE_IDS.get(did) or next((IMMUTABLE_IDS[x] for x in like if x in IMMUTABLE_IDS), "")
    if not note and (ostree_booted or "ostree" in d.variant_id or "atomic" in d.variant_id):
        note = (
            "this system is image based (ostree): system packages go through rpm-ostree. paws only writes to your home."
        )
    d.immutable_note = note
    return d


def detect(files=OS_RELEASE_FILES, ostree_marker: str = "/run/ostree-booted") -> Distro:
    for f in files:
        try:
            text = Path(f).read_text()
        except OSError:
            continue
        return from_text(text, ostree_booted=os.path.exists(ostree_marker))
    return Distro()
