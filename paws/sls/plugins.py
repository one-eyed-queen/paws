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


# ---- the download plugin ----------------------------------------------------------------------
# a plugin can read config keys the .so never does, and that's how the public build downloads. download.lua (what
# enter-the-wired and ASSella ship) does what private builds do natively: it puts AdditionalDepots into package 0 so
# steam counts those depots as yours, hands steam the DecryptionKeys when it asks its config store for a depot key,
# and fetches the manifest request code valve refuses for a game you don't own. without it every game on a public
# build sits at 0 B, and steam deletes an unlicensed game's files at its next start

DOWNLOAD = "download.lua"
# byte for byte the download.lua in enter-the-wired's release, ASSella and lumaforge-panel. paws installs this one
# only: a plugin runs any code it likes inside steam
DOWNLOAD_SHA256 = "8e822aecfea085cfcada45b9ed0e8f2c09bc04b76c667cc1904342c9197be627"
DOWNLOAD_SOURCES = (
    ("https://github.com/ciscosweater/enter-the-wired/releases/download/latest/plugins-deps.zip", DOWNLOAD),
    (
        (
            "https://raw.githubusercontent.com/niwia/ASSella/f7a9fd754610953fa842e346e6fce04185ff32ba/"
            "src/res/plugins/download.lua"
        ),
        None,
    ),
)
DOWNLOAD_KEYS = frozenset({"AdditionalDepots", "DecryptionKeys"})

_READS = re.compile(r'SLS\.config:get\w*\(\s*"(\w+)"')
_PATTERNS = re.compile(r'patternScan\(\s*"([0-9A-Fa-f? ]+)"')
_FACTS: dict = {}


def live_files() -> list[Path]:
    """the .lua files SLSsteam runs (plugins-disabled is paws' own folder, it never looks there)"""
    try:
        return sorted(p for p in plugins_dir().glob("*.lua") if p.is_file())
    except OSError:
        return []


def _facts(path: Path) -> tuple[frozenset[str], tuple[str, ...], bool, str]:
    """(config keys it reads, its byte patterns, whether it does downloads, sha256), remembered per file version"""
    import hashlib

    stamp = (str(path), path.stat().st_mtime_ns)
    if stamp not in _FACTS:
        raw = path.read_bytes()
        text = raw.decode(errors="replace")
        reads = frozenset(_READS.findall(text))
        downloads = DOWNLOAD_KEYS <= reads and "GetManifestRequestCode" in text
        _FACTS[stamp] = (reads, tuple(_PATTERNS.findall(text)), downloads, hashlib.sha256(raw).hexdigest())
    return _FACTS[stamp]


def keys_read() -> frozenset[str]:
    """config keys the live plugins read. none when SLSsteam doesn't run them (Plugins isn't on)"""
    if not master_on():
        return frozenset()
    out: set[str] = set()
    for path in live_files():
        try:
            out |= _facts(path)[0]
        except OSError:
            continue
    return frozenset(out)


def downloader() -> Path | None:
    """the live plugin that does downloads, whatever it's called"""
    for path in live_files():
        try:
            if _facts(path)[2]:
                return path
        except OSError:
            continue
    return None


def download_ready() -> bool:
    return master_on() and downloader() is not None


def steam_client() -> Path | None:
    """the 32-bit steamclient.so SLSsteam and its plugins hook"""
    try:
        from ..steam.find import find_steam

        steam = find_steam()
    except (ImportError, OSError):
        return None
    if not steam or not steam.root:
        return None
    client = Path(steam.root) / "ubuntu12_32" / "steamclient.so"
    return client if client.is_file() else None


_CODE: dict = {}


def missing_patterns(path: Path) -> list[str] | None:
    """the plugin's byte patterns this steam client doesn't have. a steam update moves code around, and a plugin that
    can't find its spot can't hook it. None when there's no client or nothing to check"""
    from ..util import elf

    client = steam_client()
    try:
        patterns = _facts(path)[1]
        if client is None or not patterns:
            return None
        stamp = (str(client), client.stat().st_mtime_ns)
        if stamp not in _CODE:
            _CODE.clear()
            _CODE[stamp] = elf.code(client)
    except OSError:
        return None
    code = _CODE[stamp]
    return [p for p in patterns if not elf.matches(p, code)] if code else None


def fetch_download() -> bytes:
    import hashlib
    import io

    from ..util import http

    tried = []
    for url, member in DOWNLOAD_SOURCES:
        try:
            data = http.get(url, timeout=30)
            if member:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    data = archive.read(member)
        except Exception as error:
            tried.append(f"{url}: {error}")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest == DOWNLOAD_SHA256:
            return data
        tried.append(f"{url}: a different download.lua (sha256 {digest[:12]}), not the one paws checked")
    raise SlsError("couldn't get download.lua. " + "; ".join(tried))


def _steam_closed():
    from ..steam import is_running

    if is_running():
        raise SlsError(
            "close steam first: SLSsteam loads plugins when steam starts, and its author warns against swapping one "
            "under a running steam"
        )


def install_download(data: bytes | None = None) -> dict:
    """download.lua in, Plugins on, DisableUpdates off and the two sections it reads in the config.

    SLSsteam runs plugins at steam's start and on a .lua change, never on a config change (lua.cpp, config.cpp). so
    with Plugins off the file goes in first (that change runs nothing) and Plugins goes on after it: the plugin loads
    at the next start, nothing gets hooked into a running steam. with Plugins already on, writing it would do exactly
    that, so steam has to be closed then.

    DisableUpdates makes SLSsteam fail IClientAppManager::GetUpdateInfo for every AdditionalApps game. that's where
    steam's ui gets a download's size and progress, so with it on the game shows 0 B next to its bar"""
    import hashlib
    import os

    from .. import config
    from ..steam import is_running

    running = is_running()
    if running and master_on():
        _steam_closed()
    other = downloader()
    if other is not None and other.name != DOWNLOAD:
        raise SlsError(f"{other.name} already does downloads: two of them would hook the same functions")
    data = data if data is not None else fetch_download()
    if hashlib.sha256(data).hexdigest() != DOWNLOAD_SHA256:
        raise SlsError("that isn't the download.lua paws checked, so it wasn't installed")
    folder = plugins_dir()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)  # SLSsteam won't load from a plugins folder others can write to
    parked = disabled_dir() / DOWNLOAD
    if parked.is_file():
        parked.unlink()
    target = folder / DOWNLOAD
    part = folder / (DOWNLOAD + ".part")
    part.write_bytes(data)
    os.chmod(part, 0o600)
    part.replace(target)
    was_on = master_on()
    updates_were_off = (config.get_scalar("DisableUpdates") or "").strip().lower() in ("yes", "true", "on", "1")
    with config.batch():
        if not was_on:
            set_master(True)
        if updates_were_off:
            config.set_scalar("DisableUpdates", "no")
        added = config.fill_missing(only=DOWNLOAD_KEYS)
    return {
        "ok": True,
        "path": str(target),
        "plugins_turned_on": not was_on,
        "updates_turned_on": updates_were_off,
        "sections_added": added,
        "restart_steam": running,
    }


def remove_download() -> dict:
    """download.lua goes to plugins-disabled, the same as Enable/Disable does, so it can come back"""
    _steam_closed()
    if not (plugins_dir() / DOWNLOAD).is_file():
        return {"ok": True, "removed": None}
    parked = disable(DOWNLOAD[: -len(".lua")])
    return {"ok": True, "removed": str(parked.path)}
