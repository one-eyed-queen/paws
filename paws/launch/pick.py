from __future__ import annotations

import os
import shutil
from collections.abc import Mapping

from .argv import _SPECS, FALLBACK_ORDER

_ENV_HINTS = (
    ("KITTY_WINDOW_ID", "kitty"),
    ("KONSOLE_VERSION", "konsole"),
    ("KONSOLE_DBUS_SESSION", "konsole"),
    ("ALACRITTY_SOCKET", "alacritty"),
    ("ALACRITTY_LOG", "alacritty"),
    ("WEZTERM_PANE", "wezterm"),
    ("WEZTERM_EXECUTABLE", "wezterm"),
    ("GNOME_TERMINAL_SCREEN", "gnome-terminal"),
    ("GHOSTTY_RESOURCES_DIR", "ghostty"),
    ("FOOT_PID", "foot"),
)


_DESKTOP_TERMINALS = (
    ("KDE", ("konsole",)),
    ("GNOME", ("ptyxis", "gnome-terminal", "kgx")),
    ("X-CINNAMON", ("gnome-terminal",)),
    ("XFCE", ("xfce4-terminal",)),
    ("MATE", ("mate-terminal",)),
    ("LXQT", ("qterminal",)),
    ("LXDE", ("lxterminal",)),
    ("COSMIC", ("cosmic-term",)),
    ("DEEPIN", ("deepin-terminal",)),
    ("DDE", ("deepin-terminal",)),
    ("BUDGIE", ("gnome-terminal", "tilix")),
)


_TERM_HINTS = (
    ("xterm-kitty", "kitty"),
    ("alacritty", "alacritty"),
    ("foot", "foot"),
    ("xterm-ghostty", "ghostty"),
)


def current_terminal(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    for env_var, name in _ENV_HINTS:
        if env.get(env_var):
            return name
    prog = (env.get("TERM_PROGRAM") or "").lower()
    if prog in _SPECS or prog == "wezterm":
        return prog
    term = env.get("TERM", "")
    for prefix, name in _TERM_HINTS:
        if term == prefix or term.startswith(prefix):
            return name
    return None


def desktop_terminals(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    env = os.environ if env is None else env
    desktops = {
        d.strip().upper() for d in (env.get("XDG_CURRENT_DESKTOP") or "").replace(";", ":").split(":") if d.strip()
    }
    out = []
    for name, terms in _DESKTOP_TERMINALS:
        if name in desktops:
            out.extend(terms)
    return tuple(out)


def saved_terminal() -> str | None:
    from .. import settings

    name = str(settings.get_setting("terminal") or "auto")
    return None if name == "auto" else name


def installed_terminals(env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    return [t for t in FALLBACK_ORDER if shutil.which(t, path=env.get("PATH"))]


def candidates(env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    order = [
        env.get("PAWS_TERMINAL"),
        saved_terminal() if env is os.environ else None,
        current_terminal(env),
        env.get("TERMINAL"),
        "xdg-terminal-exec",
        *desktop_terminals(env),
        *FALLBACK_ORDER,
    ]
    out = []
    for name in order:
        if not name or name in out:
            continue
        if shutil.which(name, path=env.get("PATH")):
            out.append(name)
    return out
