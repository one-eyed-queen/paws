from __future__ import annotations

import importlib

NAMES = (
    "menu",
    "doctor",
    "add",
    "remove",
    "activate",
    "drop",
    "edit",
    "sls",
    "plugins",
    "alias",
    "desktop",
    "tickets",
    "art",
    "settings",
    "update",
    "launch",
    "notify",
    "fix",
    "backups",
)


def __getattr__(name: str):
    if name == "COMMANDS":
        mods = [importlib.import_module(f"{__name__}.{n}") for n in NAMES]
        commands = {m.NAME: m for m in mods}
        globals()["COMMANDS"] = commands
        return commands
    raise AttributeError(name)
