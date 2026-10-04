"""the windows side of paws. same tool, same menus: these are just the bits windows does differently
(folders, the registry, steam.exe, the console window). SLSsteam itself is linux only, its windows ports are stubbed
in port.py for now. everything here is safe to import on linux too"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"

__all__ = ["IS_WINDOWS"]
