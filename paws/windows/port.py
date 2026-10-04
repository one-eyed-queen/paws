"""SLSsteam is linux only. on windows it has two ports: HubCapTools and OpenValve (not out yet).
everything that depends on how a port is installed or loaded is stubbed here until we know more about them
(HubCapTools details, OpenValve's release and source). config.yaml, games, keys and steam itself work already."""

from __future__ import annotations

from pathlib import Path

UNDER_CONSTRUCTION = (
    "windows support is under construction: installing, updating, removing and activating with SLSsteam's windows "
    "ports (HubCapTools, OpenValve) comes once we know how they work. adding games to the config works already"
)


def find(config: Path | None):
    """the port, found by its config only. no guessing at dll names until we know them"""
    from ..paths import config_dirs
    from ..sls.model import SlsInstall
    from ..util import fs

    found = [c for c in (config, *(d / "config.yaml" for d in config_dirs())) if c is not None and fs.exists(c)]
    if not found:
        return None
    sls = SlsInstall(kind="windows", config=found[0])
    sls.cache, sls.plugins = sls.config.parent / "cache", sls.config.parent / "plugins"
    return sls


def injected() -> bool:
    return False  # stub: don't know how to tell a port is loaded into steam yet


def unsupported():
    from ..sls.errors import SlsError

    raise SlsError(UNDER_CONSTRUCTION)
