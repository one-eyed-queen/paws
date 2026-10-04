from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .schema import SECTIONS

MAX_APPID = 4294967295
KEY_LINE = re.compile(r"^\s*([A-Za-z]\w*):(?:\s|$)")
YES = {"yes", "true", "on", "y"}
NO = {"no", "false", "off", "n"}
YES_LIKE = {"1", "enabled", "enable"}
NO_LIKE = {"0", "disabled", "disable"}
SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


@dataclass
class Fix:
    line: int
    before: str
    after: str | None
    why: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.why}"


@dataclass
class Healed:
    text: str
    fixed: list[Fix] = field(default_factory=list)
    stuck: list[Fix] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stuck and yaml_ok(self.text)


def yaml_ok(text):
    try:
        yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    return True


def yaml_problem(text):
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        reason = str(getattr(error, "problem", None) or error).splitlines()[0]
        return (mark.line + 1 if mark is not None else 0), reason
    return None


def _kind(name):
    return SECTIONS["sections"][name]["type"]


def _split_comment(body):
    # value part and trailing comment, ignoring a # inside quotes
    quote = ""
    for i, ch in enumerate(body):
        if ch in "\"'":
            quote = "" if quote == ch else (quote or ch)
        elif ch == "#" and not quote and (i == 0 or body[i - 1] in " \t"):
            return body[:i].rstrip(), " " + body[i:]
    return body.rstrip(), ""


def _want_indent(kind, body, has_value):
    # where a line of this shape belongs under a section of this kind
    if kind.startswith("list") or kind in ("map-int", "map-str", "idle"):
        return 2
    if kind == "map-map":
        return 4 if has_value else 2
    if kind == "map-list":
        return 4 if body.startswith("-") else 2
    return None


def reindent(lines):
    out, fixes, section = [], [], None
    for number, line in enumerate(lines, 1):
        body = line.strip()
        if not body or body.startswith("#"):
            out.append(line)
            continue
        found = KEY_LINE.match(line)
        if found and found.group(1) in SECTIONS["sections"]:
            section = found.group(1)
            want = 0
        elif section is None:
            out.append(line)
            continue
        else:
            has_value = bool(re.match(r"^[^\s:]+:\s+\S", body))
            want = _want_indent(_kind(section), body, has_value)
        have = len(line) - len(line.lstrip(" "))
        if want is None or have == want:
            out.append(line)
            continue
        out.append(" " * want + body)
        fixes.append(Fix(number, line, out[-1], f"indent was {have}, moved to {want}"))
    return out, fixes


def _tidy_line(line):
    # small typos that break yaml and only have one sensible reading
    body = line.strip()
    if not body or body.startswith("#"):
        return line, ""
    indent = line[: len(line) - len(line.lstrip(" "))]
    text, comment = _split_comment(body)
    why = ""
    fixed = text.translate(SMART_QUOTES)
    if fixed != text:
        why = "curly quotes replaced with plain ones"
    dash = re.match(r"^-\s*(\d+)\s*,?$", fixed)
    if dash and fixed != f"- {dash.group(1)}":
        fixed, why = f"- {dash.group(1)}", why or "list item written as - <id>"
    pair = re.match(r"^(\d+|[A-Za-z]\w*):(\S.*)$", fixed)
    if pair and not fixed.startswith(("http", "0x")) and "://" not in fixed:
        fixed, why = f"{pair.group(1)}: {pair.group(2)}", why or "missing space after the colon"
    if fixed.count('"') % 2 == 1 and re.search(r':\s+"[^"]*$', fixed):
        fixed, why = fixed + '"', why or "quote was never closed"
    value = re.match(r"^(\d+):\s+([^\"'\s].*: .*)$", fixed)
    if value:
        quoted = value.group(2).replace("\\", "\\\\").replace('"', '\\"')
        fixed, why = f'{value.group(1)}: "{quoted}"', why or "value has a colon in it, put in quotes"
    if not why:
        return line, ""
    return indent + fixed + comment, why


def _mend(text):
    lines = text.replace("\t", "  ").split("\n")
    fixes = []
    for i, line in enumerate(lines):
        new, why = _tidy_line(line)
        if why:
            lines[i] = new
            fixes.append(Fix(i + 1, line, new, why))
    tabbed = [n for n, line in enumerate(text.split("\n"), 1) if "\t" in line]
    if tabbed:
        fixes.insert(
            0, Fix(tabbed[0], "", None, f"tabs aren't allowed in yaml, turned into spaces (lines {tabbed[:5]})")
        )
    return lines, fixes


def check_values(text, online_ids=None):
    """values that don't fit their key. returns (fixed text, fixes made, problems left for a person)"""
    lines = text.split("\n")
    fixes, stuck = [], []
    section = None

    def fix(i, new, why):
        fixes.append(Fix(i + 1, lines[i], new, why))
        lines[i] = new

    def bad(i, why):
        stuck.append(Fix(i + 1, lines[i], None, why))

    for i, line in enumerate(lines):
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        found = KEY_LINE.match(line)
        if found and found.group(1) in SECTIONS["sections"] and not line[0].isspace():
            section = found.group(1)
            kind = _kind(section)
            value, comment = _split_comment(body.split(":", 1)[1].strip())
            if kind in ("bool", "int", "hex"):
                _check_scalar(i, section, kind, value, comment, fix, bad)
            continue
        if section is None:
            continue
        _check_entry(i, line, _kind(section), fix, bad)
    return "\n".join(lines), fixes, stuck


def _check_scalar(i, name, kind, value, comment, fix, bad):
    plain = value.strip("\"'").strip()
    default = SECTIONS["scalar_defaults"].get(name, "")
    if kind == "bool":
        low = plain.lower()
        if low in YES | NO and plain == value:
            return
        answer = "yes" if low in YES | YES_LIKE else "no" if low in NO | NO_LIKE else None
        if answer:
            fix(i, f"{name}: {answer}{comment}", f"{name} should be yes or no, read '{plain}' as {answer}")
        else:
            bad(i, f"{name} should be yes or no, not '{plain}'")
    elif kind == "int":
        if plain.isdigit() and plain == value:
            return
        if plain.isdigit():
            fix(i, f"{name}: {plain}{comment}", f"{name} is a number, took the quotes off")
        elif not plain and default:
            fix(i, f"{name}: {default}{comment}", f"{name} was empty, put back its default {default}")
        else:
            bad(i, f"{name} should be a whole number, not '{plain}'")
    elif kind == "hex" and not re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", plain):
        if not plain and default:
            fix(i, f"{name}: {default}{comment}", f"{name} was empty, put back its default {default}")
        else:
            bad(i, f"{name} should look like 0x1 (hex) or a number, not '{plain}'")


def _appid(token):
    token = token.strip().strip("\"'").strip()
    return token if token.isdigit() and 0 <= int(token) <= MAX_APPID else None


def _check_entry(i, line, kind, fix, bad):
    if kind not in ("list-int", "map-int", "map-map", "map-list"):
        return
    indent = line[: len(line) - len(line.lstrip(" "))]
    text, comment = _split_comment(line.strip())
    if kind == "list-int" or (kind == "map-list" and text.startswith("-")):
        item = text.lstrip("-").strip().rstrip(",")
        good = _appid(item)
        if good is None:
            bad(i, f"'{item}' isn't an app id (digits only, up to {MAX_APPID})")
        elif item != good:
            fix(i, f"{indent}- {good}{comment}", f"app id {good} had quotes around it")
        return
    key, sep, value = text.partition(":")
    if not sep:
        return
    if kind == "map-map" and value.strip():
        key_ok = _appid(key)
        if key_ok is None:
            bad(i, f"'{key.strip()}' isn't a DLC id (digits only)")
        return
    if kind == "map-list":
        if not key.strip().isdigit():
            bad(i, f"'{key.strip()}' isn't a steam id (digits only)")
    elif _appid(key) is None:
        bad(i, f"'{key.strip()}' isn't an app id (digits only, up to {MAX_APPID})")
    elif kind == "map-int" and value.strip() and not value.strip().strip("\"'").isdigit():
        bad(i, f"'{value.strip()}' should be a number")


def heal(text):
    """fix what has one obvious fix, say where the rest is. never throws data away"""
    if yaml_ok(text):
        new, fixed, stuck = check_values(text)
        return Healed(new, fixed, stuck)
    lines, fixed = _mend(text)
    if not yaml_ok("\n".join(lines)):
        lines, moved = reindent(lines)
        fixed += moved
    text = "\n".join(lines)
    if not yaml_ok(text):
        problem = yaml_problem(text)
        stuck = [Fix(problem[0], "", None, f"yaml still can't read this: {problem[1]}")] if problem else []
        return Healed(text, fixed, stuck)
    new, more, stuck = check_values(text)
    return Healed(new, fixed + more, stuck)


def comment_out_stuck(text: str, stuck: list[Fix]) -> str:
    """neutralize a line paws can't safely guess a fix for by turning it into a comment.
    nothing is deleted - the original text stays right there, just inert until fixed by hand"""
    lines = text.split("\n")
    for f in stuck:
        i = f.line - 1
        if 0 <= i < len(lines) and not lines[i].lstrip().startswith("#"):
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = f"{indent}# {lines[i].strip()}  # paws commented this out: {f.why}"
    return "\n".join(lines)


APPID_SECTIONS = ("AppIds", "AdditionalApps", "FakeOffline", "AppTokens", "FakeAppIds", "LaunchOptions", "DlcData")


def app_ids_with_lines(text):
    found, section = {}, None
    for number, line in enumerate(text.split("\n"), 1):
        body = _split_comment(line.strip())[0]
        if not body:
            continue
        head = KEY_LINE.match(line)
        if head and head.group(1) in SECTIONS["sections"] and not line[0].isspace():
            section = head.group(1)
            continue
        if section not in APPID_SECTIONS:
            continue
        kind = _kind(section)
        if kind == "list-int" and body.startswith("-"):
            token = body.lstrip("-").strip()
        elif kind in ("map-int", "map-str") or (
            kind == "map-map" and line.startswith("  ") and not line.startswith("   ")
        ):
            token = body.split(":", 1)[0]
        else:
            continue
        good = _appid(token)
        if good and good != "0":
            found.setdefault(good, number)
    return found
