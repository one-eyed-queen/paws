from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..config.scalars import get_scalar, set_scalar
from ..manifest.lua import LuaManifest
from ..paths import default_config_dir
from ..util.backup import backup_file
from .errors import SlsError

NAME_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,63}")
META_LINE = re.compile(r"^--\s*([A-Za-z][\w ]*):\s*(.*?)\s*$")
MAX_ZIP_BYTES = 512 * 1024


def plugins_dir() -> Path:
    """where SLSsteam itself reads .lua plugins from and hot-reloads on any change"""
    return default_config_dir() / "plugins"


def disabled_dir() -> Path:
    """paws' own holding pen: a plugin sitting here is off, SLSsteam never sees it"""
    return default_config_dir() / "plugins-disabled"


def valid_name(name: str) -> bool:
    return bool(NAME_OK.fullmatch(name.strip()))


def master_on() -> bool:
    return (get_scalar("Plugins") or "no").strip().lower() in ("yes", "true", "on", "1")


def set_master(on: bool) -> None:
    set_scalar("Plugins", "yes" if on else "no")


def read_meta(path: Path) -> dict[str, str]:
    """the `-- key: value` comment lines at the top of the file, however many of them there are"""
    meta: dict[str, str] = {}
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return meta
    for line in lines:
        if not line.strip():
            continue
        found = META_LINE.match(line)
        if not found:
            break
        meta[found.group(1).strip().lower()] = found.group(2)
    return meta


@dataclass
class Plugin:
    name: str
    path: Path
    enabled: bool
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.meta.get("name") or self.name

    @property
    def author(self) -> str:
        return self.meta.get("author", "")

    @property
    def version(self) -> str:
        return self.meta.get("version", "")

    @property
    def desc(self) -> str:
        return self.meta.get("desc", "")


def list_plugins() -> list[Plugin]:
    out = []
    for folder, enabled in ((plugins_dir(), True), (disabled_dir(), False)):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.lua")):
            out.append(Plugin(path.stem, path, enabled, read_meta(path)))
    return sorted(out, key=lambda p: p.name.lower())


def find(name: str) -> Plugin | None:
    return next((p for p in list_plugins() if p.name == name), None)


def _slug(name: str) -> str:
    """a lua-safe global table name for the template: letters, digits, underscore, never starting with a digit"""
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "Plugin"
    return f"P_{slug}" if slug[0].isdigit() else slug


TEMPLATE = """-- name: {name}
-- author: {author}
-- version: {version}
-- desc: {desc}

-- a plugin is plain lua, hot reloaded by SLSsteam whenever this file changes (see docs/Lua in SLSsteam's repo
-- for the full api: log, curl, memhlp, LuaHook, LuaMutex, CConfig...). the guard below keeps it from running
-- its setup twice if SLSsteam reloads it.
{slug} = {slug} or {{ setup = false }}
if {slug}.setup then
    return
end
{slug}.setup = true

log.info("{name} loaded")

-- your code goes here
"""


def new_plugin(name: str, author: str = "", version: str = "1.0.0", desc: str = "", enabled: bool = False) -> Plugin:
    if not valid_name(name):
        raise SlsError("a plugin name can use letters, digits, spaces, - and _ (and can't start with one of those)")
    if find(name) is not None:
        raise SlsError(f"there's already a plugin called {name}")
    folder = plugins_dir() if enabled else disabled_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.lua"
    path.write_text(TEMPLATE.format(name=name, author=author, version=version, desc=desc, slug=_slug(name)))
    return Plugin(name, path, enabled, read_meta(path))


def enable(name: str) -> Plugin:
    plugin = find(name)
    if plugin is None:
        raise SlsError(f"no plugin called {name}")
    if plugin.enabled:
        return plugin
    plugins_dir().mkdir(parents=True, exist_ok=True)
    target = plugins_dir() / plugin.path.name
    plugin.path.rename(target)
    return Plugin(name, target, True, plugin.meta)


def disable(name: str) -> Plugin:
    plugin = find(name)
    if plugin is None:
        raise SlsError(f"no plugin called {name}")
    if not plugin.enabled:
        return plugin
    disabled_dir().mkdir(parents=True, exist_ok=True)
    target = disabled_dir() / plugin.path.name
    plugin.path.rename(target)
    return Plugin(name, target, False, plugin.meta)


def remove(name: str) -> str:
    plugin = find(name)
    if plugin is None:
        raise SlsError(f"no plugin called {name}")
    kept = backup_file(plugin.path)
    plugin.path.unlink()
    return f"removed {name}" + (f" (a copy is in the backups: {kept})" if kept else "")


def _looks_like_a_manifest_lua(path: Path) -> bool:
    """the depot-key generators dropped on the game-add screen are also .lua, but they're data, not a plugin"""
    manifest = LuaManifest(path)
    manifest.parse()
    return bool(manifest.app_ids or manifest.app_tokens or manifest.manifest_ids or manifest.decryption_keys)


def _unique_path(folder: Path, stem: str) -> Path:
    candidate = folder / f"{stem}.lua"
    n = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({n}).lua"
        n += 1
    return candidate


def import_plugin(source: Path, enabled: bool = False) -> Plugin:
    """a .lua file, or a .zip with exactly one .lua in it (paws' own export, or one someone shared)"""
    source = Path(source).expanduser()
    if not source.is_file():
        raise SlsError(f"no such file: {source}")
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            luas = [n for n in archive.namelist() if n.lower().endswith(".lua") and not n.endswith("/")]
            if len(luas) != 1:
                raise SlsError(f"expected exactly one .lua inside the zip, found {len(luas)}")
            data = archive.read(luas[0])
            stem = Path(luas[0]).stem
    elif source.suffix.lower() == ".lua":
        data = source.read_bytes()
        stem = source.stem
    else:
        raise SlsError("that's not a .lua file or a .zip with one inside")
    if len(data) > MAX_ZIP_BYTES:
        raise SlsError("that's way bigger than a plugin should be")
    text = data.decode(errors="replace")
    folder = plugins_dir() if enabled else disabled_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique_path(folder, stem)
    target.write_text(text)
    if _looks_like_a_manifest_lua(target):
        target.unlink()
        raise SlsError(
            f"{source.name} looks like a depot-key .lua (from a game), not a plugin: add it as a game instead"
        )
    return Plugin(target.stem, target, enabled, read_meta(target))


def export_plugin(name: str, dest_dir: Path) -> Path:
    plugin = find(name)
    if plugin is None:
        raise SlsError(f"no plugin called {name}")
    dest_dir = Path(dest_dir).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{plugin.name}.paws-plugin.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(plugin.path, plugin.path.name)
    return target
