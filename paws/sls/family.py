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
    "HeadCrab": "an SLSsteam build that ships its own installer",
    "Hollow": "an SLSsteam build (HollowSteam)",
    "hollow-decky": "Steam Deck / Game Mode front-end for SLSsteam",
    "SLSConfig-Decky": "Steam Deck / Game Mode editor for the SLSsteam config",
}

# other editors of the same config.yaml, by the command they put on PATH
COMPANIONS: dict[str, str] = {
    "slsconfigurator": "a TUI that edits the SLSsteam config",
}


def companions() -> list[str]:
    import shutil

    return [name for name in COMPANIONS if shutil.which(name)]

# Decky Loader keeps its plugins here; the SLSsteam-family ones edit the same config paws does
DECKY_PLUGINS = HOME / "homebrew" / "plugins"
_MARKERS = ("hollow", "slsconfig", "headcrab", "sls")


def decky_tools() -> list[str]:
    """SLSsteam-family Decky / Steam Deck plugins installed on this machine, by folder name"""
    found: list[str] = []
    try:
        entries = sorted(DECKY_PLUGINS.iterdir()) if DECKY_PLUGINS.is_dir() else []
    except OSError:
        return found
    for p in entries:
        if any(m in p.name.lower() for m in _MARKERS):
            found.append(p.name)
    return found


def present() -> list[str]:
    """named SLSsteam-family tools found beyond the core .so (so Doctor can say it recognises them)"""
    from . import headcrab

    names: list[str] = []
    try:
        if headcrab.footprint():
            names.append("HeadCrab")
    except Exception:
        pass
    names += decky_tools()
    return names
