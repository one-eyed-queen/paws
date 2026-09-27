from __future__ import annotations

import re

import yaml

from .entries import add_entry, remove_rendered
from .io import batch, raw_lines
from .schema import SECTIONS, ConfigError, section_meta
from .scalars import set_scalar
from .where import find_config

GROUPS = (
    ("", "General"),
    ("manage", "Games"),
    ("game", "Per game"),
    ("safety", "Safety"),
    ("system", "System"),
    ("misc", "Look & feel"),
    ("expert", "Expert"),
)
_GROUP_NAME = dict(GROUPS)

BOOL, VALUE, ROWS, NESTED = "bool", "value", "rows", "nested"


def group_of(key: str) -> str:
    return _GROUP_NAME.get(SECTIONS["sections"][key].get("tool", ""), "Expert")


def ordered_keys() -> list[str]:
    names = [name for name, _t, _d in section_meta()]
    rank = {tag: i for i, (tag, _n) in enumerate(GROUPS)}
    return sorted(names, key=lambda n: rank.get(SECTIONS["sections"][n].get("tool", ""), len(GROUPS)))


def mode(key: str) -> str:
    t = SECTIONS["sections"][key]["type"]
    if t == "bool":
        return BOOL
    if t in ("int", "str", "hex"):
        return VALUE
    if t in ("list-int", "map-int", "map-str"):
        return ROWS
    return NESTED


def default_of(key: str) -> str | None:
    return SECTIONS.get("scalar_defaults", {}).get(key)


_KEY_LINE = re.compile(r"^([A-Za-z]\w*):[ \t]*(.*)$")


class Snapshot:
    def __init__(self):
        self.scalars: dict[str, str] = {}
        self.blocks: dict[str, list[str]] = {}
        key = None
        for line in raw_lines():
            m = _KEY_LINE.match(line)
            if m:
                key = m.group(1)
                self.scalars.setdefault(key, m.group(2).strip())
                self.blocks.setdefault(key, [])
            elif line.strip() and not line.startswith((" ", "\t")):
                key = None
            elif key is not None:
                text = line.strip()
                if text and not text.startswith("#"):
                    self.blocks[key].append(text)


def current(key: str, snap: Snapshot | None = None) -> str:
    raw = (snap or Snapshot()).scalars.get(key)
    if raw is None:
        return default_of(key) or ""
    quoted = re.match(r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')""", raw)
    if quoted:  # a quoted string keeps its # and spaces
        try:
            return str(yaml.safe_load(quoted.group(1)))
        except yaml.YAMLError:
            return quoted.group(1)[1:-1]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def block_rows(key: str, snap: Snapshot | None = None) -> list[str]:
    return list((snap or Snapshot()).blocks.get(key, []))


def summary(key: str, snap: Snapshot | None = None) -> str:
    snap = snap or Snapshot()
    m = mode(key)
    if m == BOOL or m == VALUE:
        v = current(key, snap)
        return v if v != "" else '""'
    rows = block_rows(key, snap)
    if key == "IdleStatus":
        app_id = next((r.split(":", 1)[1].split("#")[0].strip() for r in rows if r.startswith("AppId:")), "0")
        return "off" if app_id in ("", "0") else f"app {app_id}"
    n = len(rows)
    return f"{n} row{'s' if n != 1 else ''}" if n else "empty"


def is_default(key: str, snap: Snapshot | None = None) -> bool:
    snap = snap or Snapshot()
    if mode(key) in (BOOL, VALUE):
        return current(key, snap) == (default_of(key) or "")
    return not block_rows(key, snap)


def validate_value(key: str, text: str) -> str | None:
    t = SECTIONS["sections"][key]["type"]
    text = text.strip()
    if t == "int" and not re.fullmatch(r"-?\d+", text):
        return "a whole number, like 10"
    if t == "hex" and not re.fullmatch(r"0[xX][0-9a-fA-F]+", text):
        return "hex with a 0x in front, like 0x1"
    if t == "bool" and text not in ("yes", "no"):
        return "yes or no"
    return None


def yaml_scalar(text: str) -> str:
    if text == "":
        return '""'
    out = yaml.safe_dump(text, default_flow_style=True, width=10**6).strip()
    return out.split("\n...")[0].strip()


def set_value(key: str, text: str):
    problem = validate_value(key, text)
    if problem:
        raise ValueError(problem)
    t = SECTIONS["sections"][key]["type"]
    set_scalar(key, yaml_scalar(text.strip()) if t == "str" else text.strip())


def toggle(key: str) -> str:
    new = "no" if current(key) == "yes" else "yes"
    set_scalar(key, new)
    return new


def reset(key: str) -> str:
    m = mode(key)
    if m in (BOOL, VALUE):
        d = default_of(key) or ""
        set_scalar(key, yaml_scalar(d) if SECTIONS["sections"][key]["type"] == "str" else d)
        return d
    raise ConfigError(f"{key} has rows: remove them one by one, or use the editor")


ROW_HELP = {
    "list-int": "an AppId, then an optional comment:  480 # Spacewar",
    "map-int": "id: value, then an optional comment:  480: 12345 # name",
    "map-str": 'id: "text", then an optional comment:  480: "value" # name',
}


def row_problem(key: str, text: str) -> str | None:
    t = SECTIONS["sections"][key]["type"]
    text = text.strip()
    if not text:
        return "type something first"
    if t == "list-int" and not re.match(r"\d+(\s+#.*)?$", text):
        return "start with the AppId (numbers), like: 480 # Spacewar"
    if t in ("map-int", "map-str") and not re.match(r"\d+\s*:\s*\S", text):
        return "write it as  id: value  (like 480: 12345)"
    return None


def add_row(key: str, text: str) -> str:
    problem = row_problem(key, text)
    if problem:
        raise ValueError(problem)
    t = SECTIONS["sections"][key]["type"]
    line = ("  - " if t == "list-int" else "  ") + text.strip()
    with batch():
        added, _bak = add_entry(key, line)
        if not added:
            raise ValueError("that one is already there")
        bad = _file_problem()
        if bad:
            raise ValueError(f"that would break the file ({bad})")
    return line


def remove_row(key: str, row: str) -> bool:
    removed, _bak = remove_rendered(key, row)
    return removed


def _file_problem():
    from ..editor import yaml_problem

    return yaml_problem("\n".join(raw_lines()) + "\n")


def file_problem() -> str | None:
    path = find_config()
    if path is None or not path.exists():
        return None
    from ..editor import yaml_problem

    return yaml_problem(path.read_text())
