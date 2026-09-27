from __future__ import annotations

import locale
import os
import shutil
from collections.abc import Mapping

from ..launch import current_terminal
from ..util import pkgmgr
from .result import CheckResult


def _session(env):
    kind = env.get("XDG_SESSION_TYPE") or (
        "wayland" if env.get("WAYLAND_DISPLAY") else "x11" if env.get("DISPLAY") else ""
    )
    desktop = env.get("XDG_CURRENT_DESKTOP") or env.get("DESKTOP_SESSION") or ""
    return " / ".join(x for x in (kind or "no graphical session", desktop) if x)


def term_checks(env: Mapping[str, str] | None = None) -> list:
    env = os.environ if env is None else env
    out = [CheckResult(True, "Desktop", _session(env), "info")]

    term = current_terminal(env)
    out.append(
        CheckResult(
            True,
            "Terminal",
            f"{term or 'unknown'} (TERM={env.get('TERM', '?')})",
            "info",
        )
    )

    if env.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        out.append(CheckResult(True, "Colours", "24-bit colour", "ok"))
    else:
        out.append(
            CheckResult(
                True,
                "Colours",
                "COLORTERM isn't set, so the background and gradients may look banded",
                "warn",
            )
        )

    enc = (locale.getpreferredencoding(False) or "").lower().replace("-", "")
    if "utf8" in enc:
        out.append(CheckResult(True, "Locale", "UTF-8", "ok"))
    else:
        out.append(
            CheckResult(
                False,
                "Locale",
                f"not UTF-8 ({enc or 'unknown'}): art and icons may show as ?. set LANG=en_US.UTF-8 (or C.UTF-8)",
                "warn",
            )
        )

    size = shutil.get_terminal_size((0, 0))
    if size.columns and (size.columns < 80 or size.lines < 24):
        out.append(
            CheckResult(
                False,
                "Window size",
                f"{size.columns}x{size.lines}: 80x24 or bigger is comfortable",
                "warn",
            )
        )

    graphics = "kitty" if term in ("kitty", "ghostty") else "block"
    out.append(
        CheckResult(
            True,
            "Pictures",
            {
                "kitty": "kitty graphics: sharp pictures and the glass background",
                "block": "block pictures (sharp ones need kitty or a sixel terminal)",
            }[graphics],
            "info",
        )
    )

    wayland = (env.get("XDG_SESSION_TYPE") == "wayland") or bool(env.get("WAYLAND_DISPLAY"))
    have = [t for t in (("wl-copy",) if wayland else ("xclip", "xsel")) if shutil.which(t)]
    if not have and not (wayland and shutil.which("xclip")):
        hints = pkgmgr.install_hints("wl-clipboard" if wayland else "xclip")
        how = hints[0] if hints else "install " + ("wl-clipboard" if wayland else "xclip")
        out.append(
            CheckResult(
                False,
                "Clipboard",
                f"no clipboard tool: copying tickets falls back to the terminal. {how}",
                "warn",
            )
        )
    return out
