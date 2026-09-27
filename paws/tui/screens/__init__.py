from __future__ import annotations

import importlib

_SCREENS = {
    "ActivationScreen": "activation",
    "AddGameScreen": "add_game",
    "ArtScreen": "art",
    "DoctorScreen": "doctor",
    "HomeScreen": "home",
    "PluginsScreen": "plugins",
    "RemoveGameScreen": "remove_game",
    "SectionsScreen": "sections",
    "SettingsScreen": "settings",
    "SlsScreen": "sls",
}

__all__ = sorted(_SCREENS)


def __getattr__(name: str):
    if name in _SCREENS:
        return getattr(importlib.import_module(f"{__name__}.{_SCREENS[name]}"), name)
    raise AttributeError(name)
