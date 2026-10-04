from __future__ import annotations

import os

try:
    import winreg
except ImportError:  # linux
    winreg = None

STEAM_KEYS = (
    ("HKEY_CURRENT_USER", r"Software\Valve\Steam", "SteamPath"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Valve\Steam", "InstallPath"),
)


def read(hive: str, key: str, name: str) -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(getattr(winreg, hive), key) as k:
            value, _ = winreg.QueryValueEx(k, name)
    except OSError:
        return None
    return str(value) if value not in (None, "") else None


def steam_path() -> str | None:
    """where steam lives. steam writes SteamPath itself (with / slashes) every time it starts"""
    for hive, key, name in STEAM_KEYS:
        value = read(hive, key, name)
        if value:
            return os.path.normpath(value)
    return None


def steam_exe() -> str | None:
    value = read("HKEY_CURRENT_USER", r"Software\Valve\Steam", "SteamExe")
    return os.path.normpath(value) if value else None


def shell_folder(name: str) -> str | None:
    value = read("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", name)
    return os.path.expandvars(value) if value else None


def user_path() -> list[str]:
    value = read("HKEY_CURRENT_USER", "Environment", "Path") or ""
    return [p for p in value.split(";") if p]


def add_to_user_path(folder: str) -> bool:
    """put a folder on the user's own PATH (no admin). False when it was already there"""
    if winreg is None:
        raise OSError("not on windows")
    have = user_path()
    if any(os.path.normcase(os.path.normpath(p)) == os.path.normcase(os.path.normpath(folder)) for p in have):
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "Path", 0, winreg.REG_EXPAND_SZ, ";".join([*have, folder]))
    _broadcast_env_change()
    return True


def _broadcast_env_change():
    """tell explorer the env changed so new terminals see the new PATH without a logout"""
    try:
        import ctypes

        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))
    except Exception:
        pass
