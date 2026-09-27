from __future__ import annotations

import re
from dataclasses import dataclass, field

ID = r"\d{2,10}"
_URL_RE = re.compile(
    rf"(?:store\.steampowered\.com/app|steamcommunity\.com/app|steam://(?:run|store|nav/games/details)|steam://openurl/https?://store\.steampowered\.com/app)/({ID})(?:/([^/\s?#]+))?",
    re.I,
)
_BASE_RE = re.compile(rf"(?im)^\s*(?:app\s*id|appid|app\s*#)\s*[:\t ]+({ID})\b")
_TITLE_ID_RE = re.compile(rf"(?i)\bapp\s*id\s*[:#]?\s*({ID})\b")
_DATE_TAIL_RE = re.compile(r"\s+(?:\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|[A-Z][a-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2}).*$")
_TYPES = "DLC|Game|Application|Demo|Tool|Music|Beta|Video|Hardware|Mod|Config|Series|Episode|Advertising|Driver"
_TYPE_TAIL_RE = re.compile(rf"\s+(?:{_TYPES})\b.*$")
_TYPE_ONLY_RE = re.compile(rf"(?i)^(?:{_TYPES})$")
_HEADER_RE = re.compile(r"(?i)^(?:app\s*id|appid|id|name|type|last\s*update(?:d)?|updated|dlc|depots?|price|store)\b")
_DATEISH_RE = re.compile(
    r"(?i)^(?:\d{1,2}\s+[a-z]+\s+\d{4}|[a-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})\b|\bUTC\b|\bago\b"
)
_DEPOT_HINT_RE = re.compile(r"(?i)\bdepot\s*id\b|\bmanifest\b|\bsize\s*\(?(?:gib|mib|gb|mb)|\bdepots?\b.*\bmanifest")


@dataclass
class Item:
    id: str
    name: str = ""
    note: str = ""


@dataclass
class Parsed:
    kind: str = "apps"
    base_id: str = ""
    base_name: str = ""
    items: list[Item] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [i.id for i in self.items]


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_multiline(text: str) -> bool:
    return "\n" in normalize(text).strip()


def clean_name(name: str) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name)
    name = name.replace('"', "'").replace("\\", "/")
    name = re.sub(r"\s+", " ", name).strip(" \t-–—|·:")
    return name[:80]


def _strip_tail(text):
    text = _DATE_TAIL_RE.sub("", text)
    text = _TYPE_TAIL_RE.sub("", text)
    return clean_name(text)


def _name_line(line):
    s = line.strip()
    if not s or re.fullmatch(r"[\d.,\s]+", s) or _TYPE_ONLY_RE.match(s) or _DATEISH_RE.search(s):
        return False
    return not _HEADER_RE.match(s)


def parse_text(text: str) -> Parsed:
    out = Parsed()
    if not text or not text.strip():
        return out
    lines = [l.strip() for l in normalize(text).split("\n")]
    lines = [l for l in lines if l]
    head = "\n".join(lines[:40])

    m = _BASE_RE.search(head) or _TITLE_ID_RE.search(head)
    if m:
        out.base_id = m.group(1)
    dlc_page = bool(re.search(r"(?im)^\s*(?:dlc|downloadable content)\b", head)) or bool(re.search(r"\bDLC\b", head))
    depot_page = bool(_DEPOT_HINT_RE.search(head)) and not dlc_page

    seen = {}

    def add(id_: str, name: str = "", note: str = ""):
        if not id_ or id_ == out.base_id and dlc_page:
            return
        if id_ in seen:
            if name and not seen[id_].name:
                seen[id_].name = name
            return
        seen[id_] = Item(id_, name, note)

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if _DATEISH_RE.match(line):
            continue
        if _HEADER_RE.match(line) and not re.match(rf"^{ID}\b", line):
            if m := re.match(rf"(?i)^(?:app\s*id|appid)\s*[:\t ]+({ID})\b", line):
                out.base_id = out.base_id or m.group(1)
            continue
        urls = list(_URL_RE.finditer(line))
        if urls:
            for u in urls:
                add(u.group(1), clean_name(re.sub(r"[-_+]+", " ", u.group(2))) if u.group(2) else "")
            continue
        cells = [c.strip() for c in line.split("\t") if c.strip()]
        if len(cells) >= 2 and re.fullmatch(ID, cells[0]):
            name = next((clean_name(c) for c in cells[1:] if _name_line(c)), "")
            add(cells[0], name, "DLC" if dlc_page else "")
            continue
        m = re.match(rf"^({ID})\s+(\S.*)$", line)
        if m and not re.fullmatch(r"[\d.,\s]+", m.group(2)):
            add(m.group(1), _strip_tail(m.group(2)), "DLC" if dlc_page else "")
            continue
        if re.fullmatch(ID, line):
            name = ""
            if i < len(lines) and _name_line(lines[i]) and not re.match(rf"^{ID}\b", lines[i]):
                name = _strip_tail(lines[i])
                i += 1
            add(line, name, "DLC" if dlc_page else "")
            continue
        bare = re.findall(rf"(?<![\d.])({ID})(?![\d.])", line)
        if bare and re.fullmatch(r"[\d,;\s]+", line):
            for b in bare:
                add(b)
            continue

    if not out.base_name and lines and _name_line(lines[0]) and (out.base_id or dlc_page):
        title = re.sub(r"(?i)\s+(?:dlc|downloadable content)s?\s*$", "", lines[0])
        out.base_name = clean_name(title) if len(title) < 80 else ""
    if depot_page:
        out.kind = "depots"
        out.skipped = [f"{it.id} (a depot, not an app)" for it in seen.values()]
        return out
    out.items = list(seen.values())
    if out.base_id and dlc_page or out.base_id and len(out.items) > 0 and all(it.note == "DLC" for it in out.items):
        out.kind = "dlc"
    elif out.items and all(not it.name for it in out.items):
        out.kind = "ids"
    return out
