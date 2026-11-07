"""the SLSsteam family: one engine, many names.

SLSsteam is the core - the .so paws installs and injects. Everything else people mention (HeadCrab,
Hollow / HollowSteam, the Steam Deck / Decky front-ends like hollow-decky and SLSConfig-Decky) is either
a build of that same engine or a Game Mode front-end that edits the same ~/.config/SLSsteam/config.yaml.
paws treats them all as SLSsteam so the user and the tool speak the same language."""

from __future__ import annotations

from pathlib import Path

from ..paths import HOME

# name -> one-line "what it is", SLSsteam first because it's the engine the rest are built on
KNOWN: dict[str, str] = {
    "SLSsteam": "the engine paws installs and injects (the .so)",
    "HeadCrab": "an SLSsteam build that ships its own installer and in-client downloads",
    "Hollow": "an SLSsteam build (HollowSteam) with auto ticket/key fetching",
    "hollow-decky": "Steam Deck / Game Mode front-end for HollowSteam",
    "SLSConfig-Decky": "Steam Deck / Game Mode editor for the SLSsteam config",
    "slsconfigurator": "Terminal UI for configuring SLSsteam (by petar / xamionex)",
    "TOST": "OpenSteamTool Companion Toolkit GUI by sadabx",
    "tachilabs": "Tachilabs CLI tools and manager",
}

# Decky Loader keeps its plugins here; the SLSsteam-family ones edit the same config paws does
DECKY_DIRS = (
    HOME / "homebrew" / "plugins",
    Path("/home/deck/homebrew/plugins"),
    Path("/homebrew/plugins"),
)
_MARKERS = ("hollow", "slsconfig", "headcrab", "sls")


def decky_tools() -> list[str]:
    """SLSsteam-family Decky / Steam Deck plugins installed on this machine, by folder name"""
    found: list[str] = []
    seen = set()
    for d in DECKY_DIRS:
        try:
            entries = sorted(d.iterdir()) if d.is_dir() else []
        except OSError:
            continue
        for p in entries:
            name = p.name
            if name not in seen and any(m in name.lower() for m in _MARKERS):
                seen.add(name)
                found.append(name)
    return found


def companion_tools() -> list[str]:
    """companion managers and tools detected on the system (TOST, slsconfigurator, tachilabs)"""
    import shutil

    tools: list[str] = []
    # TOST
    for p in (HOME / ".config/TOST", HOME / "TOST", HOME / ".local/share/TOST", Path("/home/deck/TOST")):
        if p.exists():
            tools.append("TOST")
            break
    # slsconfigurator
    if shutil.which("slsconfigurator") or (HOME / ".local/bin/slsconfigurator").exists():
        tools.append("slsconfigurator")
    # tachilabs
    if (Path("/tmp/tachilabs.sh")).exists() or (HOME / ".local/share/tachilabs").exists():
        tools.append("tachilabs")
    return tools


def present() -> list[str]:
    """named SLSsteam-family tools found beyond the core .so (so Doctor and Home can say it recognises them)"""
    from . import headcrab

    names: list[str] = []
    try:
        if headcrab.footprint():
            names.append("HeadCrab")
    except Exception:
        pass
    names += decky_tools()
    names += companion_tools()
    return names
