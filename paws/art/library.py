from __future__ import annotations


from .dirs import BUNDLED_DIR, user_art_dir
from .fit import fit
from .model import Art
from .parse import escape_markup, markup_lines, parse_art, plain_lines


def _scan_dir(base, out):
    if not base.exists():
        return
    for p in sorted(base.rglob("*.txt")):
        if p.name == "placeholder.txt":
            continue
        priority = 2 if p.parent.name == "colored" else (1 if p.parent.name == "black-white" else 0)
        nsfw = p.parent.name == "nsfw"
        try:
            art = parse_art(p.read_text(), p.stem, p)
        except OSError:
            continue
        art.nsfw = nsfw
        _register(out, art, priority)


def _register(out, art, priority):
    name = art.name
    prev = out.get(name)
    if prev is None:
        out[name] = (art, priority)
        return
    prev_art, prev_pri = prev
    if prev_art.nsfw != art.nsfw:
        if art.nsfw:
            art.name = f"{name} (nsfw)"
            out[art.name] = (art, priority)
        else:
            out[f"{name} (nsfw)"] = (prev_art, prev_pri)
            out[name] = (art, priority)
    elif priority >= prev_pri:
        out[name] = (art, priority)


def nsfw_allowed(explicit):
    if explicit is not None:
        return explicit
    try:
        from ..settings import get_setting

        return bool(get_setting("nsfw"))
    except Exception:
        return False


def _bundled_placeholder():
    p = BUNDLED_DIR / "placeholder.txt"
    if not p.exists():
        return None
    try:
        return parse_art(p.read_text(), "placeholder.txt", p)
    except OSError:
        return None


_CACHE: dict = {}


def _stamp(base):
    if not base.exists():
        return ()
    out = []
    for p in sorted(base.rglob("*.txt")):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(out)


def _collect():
    found = {}
    _scan_dir(user_art_dir(), found)
    bundled = {}
    _scan_dir(BUNDLED_DIR, bundled)
    seen = {tuple(a.lines) for a, _ in found.values()}
    for name, (art, pri) in bundled.items():
        if tuple(art.lines) in seen:
            continue
        key = f"{name} (bundled)" if name in found else name
        art.name = key
        found[key] = (art, pri)
    if not found:
        ph = _bundled_placeholder()
        if ph is not None:
            found[ph.name] = (ph, 0)
    return found


def library(nsfw: bool | None = None) -> dict[str, Art]:
    key = (str(user_art_dir()), _stamp(user_art_dir()), str(BUNDLED_DIR), _stamp(BUNDLED_DIR))
    if _CACHE.get("key") != key:
        _CACHE["key"], _CACHE["found"] = key, _collect()
    allow = nsfw_allowed(nsfw)
    return {name: art for name, (art, _) in _CACHE["found"].items() if allow or not art.nsfw}


def display_lines(art: Art) -> list[str]:
    src = markup_lines(art) if art.colored else plain_lines(art)
    return [escape_markup(l) for l in src]


def display_fit(art: Art, cols: int | None, rows: int | None) -> list[str]:
    plain = plain_lines(art)
    fitted = fit(plain, cols, rows)
    if fitted == plain:
        return display_lines(art)
    return [escape_markup(l) for l in fitted]
