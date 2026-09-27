from __future__ import annotations

import json

from ..paths import DATA_DIR

SECTIONS = json.loads((DATA_DIR / "sls_sections.json").read_text())


class ConfigError(Exception):
    pass


def section_schema(section):
    s = SECTIONS["sections"].get(section)
    if s is None:
        raise ConfigError(f"unknown section {section}")
    return s


def section_meta() -> list[tuple[str, str, str]]:
    order = [
        "DisableFamilyShareLock",
        "UseWhitelist",
        "AppIds",
        "AdditionalApps",
        "DlcData",
        "AppTokens",
        "CDKeys",
        "FakeOffline",
        "FakeAppIds",
        "ManifestIds",
        "DepotBlacklist",
        "IdleStatus",
        "GameTitles",
        "SubscriptionTimestamps",
        "DenuvoGames",
        "SteamIdOverride",
        "SmartTickets",
        "MaxSchemaTries",
        "LaunchOptions",
        "SafeMode",
        "WarnHashMissmatch",
        "NotifyInit",
        "API",
        "Plugins",
        "DisableCloud",
        "DisableUpdates",
        "FakeName",
        "FakeEmail",
        "FakeWalletBalance",
        "LogLevels",
        "DumpClientInterfaces",
        "ExtendedLogging",
    ]
    out = []
    for name in order:
        if name in SECTIONS["sections"]:
            s = SECTIONS["sections"][name]
            out.append((name, s["type"], s["desc"]))
    for name, s in SECTIONS["sections"].items():
        if name not in order:
            out.append((name, s["type"], s["desc"]))
    return out


def ordered_keys():
    return [name for name, _type, _desc in section_meta()]
