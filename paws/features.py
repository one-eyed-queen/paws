from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    desc: str
    icon: str
    hint: str
    module: str
    cls: str
    toggleable: bool = True
    riced_only: bool = False
    needs_sls: bool = False


FEATURES: tuple[Feature, ...] = (
    Feature(
        "status",
        "Status / Doctor",
        "What steam and SLSsteam you have and what needs updating",
        "status",
        "steam + sls checks",
        "screens.doctor",
        "DoctorScreen",
    ),
    Feature(
        "sls",
        "Install / Update SLSsteam",
        "Install, update or remove SLSsteam",
        "install",
        "install or update",
        "screens.sls",
        "SlsScreen",
    ),
    Feature(
        "add",
        "Add a game",
        "Look a game up or import its files",
        "add",
        "search, import, drop",
        "screens.add_game",
        "AddGameScreen",
        needs_sls=True,
    ),
    Feature(
        "remove",
        "Remove a game",
        "Take a game out of everything paws added",
        "remove",
        "clean removal",
        "screens.remove_game",
        "RemoveGameScreen",
        needs_sls=True,
    ),
    Feature(
        "activation",
        "Activation",
        "Make both tickets, or use ones from the cache",
        "activation",
        "make or use tickets",
        "screens.activation",
        "ActivationScreen",
        needs_sls=True,
    ),
    Feature(
        "sections",
        "Config editor",
        "Every SLSsteam setting, or open config.yaml in nvim / nano",
        "sections",
        "settings + nvim/nano",
        "screens.sections",
        "SectionsScreen",
        needs_sls=True,
    ),
    Feature(
        "plugins",
        "Plugins / Add-ons",
        "Write, import, export and switch SLSsteam's .lua plugins on or off",
        "box",
        "manage plugins",
        "screens.plugins",
        "PluginsScreen",
        needs_sls=True,
    ),
    Feature(
        "art",
        "ASCII art / banner",
        "Pick the home banner from the gallery",
        "art",
        "pick the banner",
        "screens.art",
        "ArtScreen",
        riced_only=True,
    ),
    Feature(
        "games",
        "Arcade / mini-games",
        "Tetris, snake, brick breaker and 2048",
        "games",
        "4 mini-games",
        "arcade",
        "GamesScreen",
        riced_only=True,
    ),
    Feature(
        "alias",
        "Shell alias",
        "Get the paws command into your shell",
        "alias",
        "shell snippet",
        "screens.alias",
        "AliasScreen",
    ),
    Feature(
        "settings",
        "Settings",
        "look, nsfw, terminal, menu switches",
        "settings",
        "look, terminal, more",
        "screens.settings",
        "SettingsScreen",
        toggleable=False,
    ),
)

BY_KEY: dict[str, Feature] = {f.key: f for f in FEATURES}
