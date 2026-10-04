from __future__ import annotations

import os
import re
import shlex
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import textdrop

ACCEPTED = (".manifest", ".lua", ".key")
TICKET_NAME = re.compile(r"^(?:encryptedTicket|ticket)_(\d+)\.yaml$")
MAX_TICKET_BYTES = 64 * 1024
BUILD_HINT = re.compile(r"(?i)slssteam|headcrab|ticketforge|paws")


def is_ticket_file(p: Path) -> bool:
    return bool(TICKET_NAME.match(p.name))


def _token_to_path(tok):
    if tok.startswith("file://"):  # file managers hand over percent encoded uris
        tok = unquote(urlparse(tok).path)
        if os.name == "nt" and re.match(r"/[A-Za-z]:", tok):  # file:///C:/x -> /C:/x -> C:/x
            tok = tok[1:]
    return Path(tok).expanduser()


def _zip_holds_game_files(p):
    try:
        with zipfile.ZipFile(p) as z:
            return any(Path(info.filename).suffix.lower() in ACCEPTED for info in z.infolist())
    except Exception:
        return False


def _zip_looks_like_build(p):
    try:
        with zipfile.ZipFile(p) as z:
            infos = z.infolist()
    except Exception:
        return False
    if any(Path(info.filename).suffix.lower() in ACCEPTED for info in infos):
        return False
    for info in infos:
        nm = Path(info.filename)
        base = nm.name.lower()
        if nm.suffix.lower() == ".so" or BUILD_HINT.search(info.filename):
            return True
        if base.startswith("slssteam") or base == "headcrab":
            return True
    return False


def build_zip_from_text(text: str) -> Path | None:
    paths = paths_in(text)
    if len(paths) != 1:
        return None
    p = paths[0]
    if p.suffix.lower() != ".zip" or not p.is_file():
        return None
    return p if _zip_looks_like_build(p) else None


REPO_LINK = re.compile(r"^https?://[^/\s]*(github|gitlab|codeberg|gitea|forgejo)[^/\s]*/[^/\s]+/[^/\s]+")
ARCHIVE_LINK = re.compile(r"^https?://\S+\.(zip|7z)(\?\S*)?$", re.I)
LIST_SUFFIXES = (".txt", ".csv", ".list")
MAX_LIST_BYTES = 1024 * 1024


def _sevenzip_looks_like_build(p):
    try:
        import py7zr

        with py7zr.SevenZipFile(p) as archive:
            names = archive.getnames()
    except Exception:
        return bool(BUILD_HINT.search(p.name))
    return any(n.lower().endswith(".so") or BUILD_HINT.search(n) for n in names)


def build_source_from_text(text):
    """another build of sls or headcrab: a .zip/.7z that looks like one, or a link to its repo or archive"""
    one = text.strip()
    if "\n" in one.replace("\r", "\n"):
        return None
    if re.match(r"^(https?://|git@)\S+$", one):
        if ARCHIVE_LINK.match(one) or REPO_LINK.match(one) or one.startswith("git@") or one.endswith(".git"):
            return one
        return None
    zipped = build_zip_from_text(text)
    if zipped is not None:
        return str(zipped)
    paths = paths_in(text)
    if len(paths) == 1 and paths[0].suffix.lower() == ".7z" and paths[0].is_file():
        return str(paths[0]) if _sevenzip_looks_like_build(paths[0]) else None
    return None


def list_file_text(text):
    """a .txt of app ids or a saved dlc page dropped on the window, as the text inside"""
    paths = paths_in(text)
    if not paths:
        return None
    parts = []
    for p in paths:
        try:
            if p.suffix.lower() not in LIST_SUFFIXES or not p.is_file() or p.stat().st_size > MAX_LIST_BYTES:
                return None
            parts.append(p.read_text(errors="replace"))
        except OSError:
            return None
    return "\n".join(parts)


def is_bare_id(text: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+\s*", text))


def _split(line):
    """windows terminal pastes C:\\x\\y.zip, and quotes it only when there's a space: posix shlex would eat every
    backslash as an escape, so on windows split without escapes and take the quotes off by hand"""
    if os.name != "nt":
        return shlex.split(line)
    return [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t for t in shlex.split(line, posix=False)]


def paths_in(text: str) -> list[Path]:
    out = []
    for line in text.replace("\r", "\n").split("\n"):
        line = line.strip().strip("\x00")
        if not line:
            continue
        try:
            toks = _split(line)
        except ValueError:
            toks = [line]
        out.extend(_token_to_path(t) for t in toks)
    return out


def dropped_files(text: str) -> list[Path] | None:
    paths = paths_in(text)
    if not paths:
        return None
    for p in paths:
        try:
            if not p.is_file():
                return None
            if p.suffix.lower() in ACCEPTED or is_ticket_file(p):
                continue
            if p.suffix.lower() == ".zip" and _zip_holds_game_files(p):
                continue
            return None
        except OSError:
            return None
    if any(is_ticket_file(p) for p in paths) and not all(is_ticket_file(p) for p in paths):
        return None
    seen = []
    for p in paths:
        if p not in seen:
            seen.append(p)
    return seen


@dataclass
class DropResult:
    ok: bool
    title: str
    lines: list[str] = field(default_factory=list)


def import_any(paths: list[Path]) -> DropResult:
    if paths and all(is_ticket_file(p) for p in paths):
        return import_tickets(paths)
    return import_files(paths)


def import_tickets(paths: list[Path]) -> DropResult:
    from .sls import tickets

    saved = []
    problems = []
    for p in paths:
        appid = TICKET_NAME.match(p.name).group(1)
        try:
            if p.stat().st_size > MAX_TICKET_BYTES:
                problems.append(f"{p.name}: too big to be a ticket")
                continue
            tk = tickets.save_ticket(appid, p.read_text())
            saved.append(tk.filename)
        except (OSError, ValueError, UnicodeDecodeError) as error:
            problems.append(f"{p.name}: {error}")
    if not saved:
        return DropResult(False, "no tickets added", problems or ["nothing there looked like a ticket"])
    title = f"added {len(saved)} ticket{'s' if len(saved) != 1 else ''}"
    return DropResult(not problems, title, [", ".join(saved), *problems])


def import_files(paths: list[Path]) -> DropResult:
    from .games import apply_plan, plan_from_bundle
    from .manifest.bundle import ManifestBundle

    bundle = ManifestBundle()
    problems = []
    tmp = None
    for p in paths:
        try:
            if p.suffix.lower() == ".zip":
                if tmp is None:
                    tmp = Path(tempfile.gettempdir()) / f"paws-unz-{p.stem}"
                bundle.add_archive(p, tmp)
            else:
                bundle.add_file(p)
        except Exception as error:
            problems.append(f"{p.name}: couldn't read it ({error})")
    try:
        plan = plan_from_bundle(bundle)
        has_keys_only = bool(plan.decryption_keys) and not bundle.luas
        if has_keys_only:
            plan.decryption_keys = {}
            problems.append("a .key on its own doesn't say which depot it's for: drop its .lua with it")
        changes = plan.changes()
        if not changes:
            return DropResult(False, "nothing to add", problems or ["those files didn't have anything paws can use"])
        result = apply_plan(plan)
    except Exception as error:
        return DropResult(False, "couldn't add it", [str(error), *problems])
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    counts = plan.counts()
    what = ", ".join(f"{n} to {target}" for target, n in sorted(counts.items()))
    via = " from .zip" if any(p.suffix.lower() == ".zip" for p in paths) else ""
    title = f"added {plan.appid}{via}" if plan.appid else "added"
    lines = [what, *result["errors"], *problems]
    return DropResult(not result["errors"], title, lines)


def wants_text(parsed, focus_is_input: bool = False, focus_is_textarea: bool = False, text: str = "") -> bool:
    if focus_is_textarea:
        return False
    if parsed.kind == "depots":
        return True
    if parsed.kind == "dlc" and parsed.items:
        return True
    if is_bare_id(text) and parsed.items and not focus_is_input:
        return True
    if not textdrop.is_multiline(text):
        return False
    return len(parsed.items) >= 2 and not focus_is_input


def import_text(parsed, lookup: bool = False) -> DropResult:
    from .games import apply_bulk, lookup_names, plans_from

    if parsed.kind == "depots":
        return DropResult(False, "that's a depot list", ["those ids are depots, not apps: nothing added"])
    if not parsed.items:
        return DropResult(False, "no app ids found", ["nothing in that text looked like an app id"])
    names = lookup_names([i.id for i in parsed.items if not i.name]) if lookup else {}
    plans = plans_from(parsed, names)
    try:
        result = apply_bulk(plans)
    except Exception as error:
        return DropResult(False, "couldn't add them", [str(error)])
    n = len(parsed.items)
    new = result.get("added", 0)
    if parsed.kind == "dlc" and parsed.base_id:
        base = parsed.base_name or parsed.base_id
        title = f"added {n} DLC to {base}" if new else f"{base}: nothing new"
        lines = [f"base game {parsed.base_id}", f"{new} new entr{'y' if new == 1 else 'ies'} written"]
    else:
        title = f"added {n} app(s)" if new else "nothing new"
        lines = [f"{new} new entr{'y' if new == 1 else 'ies'} written"]
    if not new:
        lines.append("everything in that text was already in your config")
    lines += result["errors"]
    return DropResult(not result["errors"], title, lines)
