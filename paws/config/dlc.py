from __future__ import annotations

import re

from ..util.backup import backup_file
from .io import raw_lines, write
from .lines import block_end_line, child_end_line, item_key, section_index
from .seed import ensure_config


def _dlc_parent(lines, index, end, appid):
    for i in range(index + 1, end):
        if re.match(rf"^\s+{re.escape(appid)}:\s*(#.*)?$", lines[i]):
            return i
    return None


def add_dlc_data(appid: str, dlc: str, name: str = "", backup: bool = True) -> tuple[bool, str]:
    path = ensure_config()
    bak = backup_file(path) if backup else None
    appid, dlc = str(appid), str(dlc)
    lines = raw_lines(path)
    line = f'    {dlc}: "{name}"'
    index = section_index(lines, "DlcData")
    if index is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines += ["DlcData:", f"  {appid}:", line]
    else:
        end = block_end_line(lines, index)
        parent = _dlc_parent(lines, index, end, appid)
        if parent is None:
            position = end
            while position > index + 1 and not lines[position - 1].strip():
                position -= 1
            lines[position:position] = [f"  {appid}:", line]
        else:
            child_end = child_end_line(lines, parent, end)
            if any(item_key(l) == dlc for l in lines[parent + 1 : child_end] if not l.lstrip().startswith("#")):
                return False, bak
            lines.insert(child_end, line)
    write(path, "\n".join(lines) + "\n")
    return True, bak


def remove_dlc_data(appid: str, dlc: str | None = None, backup: bool = True) -> bool:
    path = ensure_config()
    if backup:
        backup_file(path)
    appid = str(appid)
    lines = raw_lines(path)
    index = section_index(lines, "DlcData")
    if index is None:
        return False
    end = block_end_line(lines, index)
    parent = _dlc_parent(lines, index, end, appid)
    if parent is None:
        return False
    child_end = child_end_line(lines, parent, end)
    if dlc is None:
        del lines[parent:child_end]
    else:
        keep = [l for l in lines[parent + 1 : child_end] if item_key(l) != str(dlc)]
        if len(keep) == child_end - parent - 1:
            return False
        lines[parent + 1 : child_end] = keep
    write(path, "\n".join(lines) + "\n")
    return True
