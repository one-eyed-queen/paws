from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path

from ..paths import default_config_dir
from ..util import http
from .errors import SlsError

# paws picks the download.lua variant that matches this steam client and this SLSsteam build. the public plugin
# collection owns the list and the hashes; paws only trusts bytes whose sha256 is in that list. PAWS_PLUGIN_MANIFEST_URL
# lets someone point paws at another public collection without changing the code.
MANIFEST_URL = "https://api.github.com/repos/one-eyed-queen/paws-plugins/contents/manifest.json?ref=main"
MANIFEST_MIRRORS = (
    "https://raw.githubusercontent.com/one-eyed-queen/paws-plugins/main/manifest.json",
    "https://cdn.jsdelivr.net/gh/one-eyed-queen/paws-plugins@main/manifest.json",
)
MANIFEST_URL_ENV = "PAWS_PLUGIN_MANIFEST_URL"


def manifest_urls() -> tuple[str, ...]:
    """an optional public collection first, then paws' own repo and its mirror"""
    override = os.environ.get(MANIFEST_URL_ENV, "").strip()
    extra = tuple(u.strip() for u in override.replace(",", " ").split() if u.strip().startswith("https://"))
    return (*extra, MANIFEST_URL, *MANIFEST_MIRRORS)


MANIFEST_CACHE = default_config_dir() / "download-plugin-manifest.json"
MANIFEST_TTL = 600.0
MAX_ENTRIES = 500
MAX_PLUGIN_BYTES = 512 * 1024
_HEX64 = re.compile(r"[0-9a-f]{64}$")
_TAG = re.compile(r"\d{14}$")
COLLECTION_NAME = re.compile(r"[a-z][a-z0-9_-]{0,39}")


def sls_arch() -> int | None:
    """word size of the installed SLSsteam .so: the client that runs its lua plugins has to match it"""
    try:
        from ..util import elf
        from .find import find_sls

        sls = find_sls()
        library = getattr(sls, "sls_so", None) if sls is not None else None
        return elf.bits(library) if library is not None else None
    except (ImportError, OSError, ValueError):
        return None


def current_key() -> dict:
    """the (steam_arch, sls_arch, steam_build, sls_version) facts used to choose a plugin. missing values are empty"""
    key = {"steam_arch": 0, "sls_arch": None, "steam_build": "", "steam_channel": "", "sls_version": ""}
    key["sls_arch"] = sls_arch()
    try:
        from ..steam.find import find_steam
        from ..steam.tinker import active_bits

        steam = find_steam()
        if steam and steam.root:
            key["steam_arch"] = active_bits(Path(steam.root))
            key["steam_build"] = str(steam.client_version or "")
            key["steam_channel"] = steam.channel or ""
    except (ImportError, OSError, ValueError):
        pass
    try:
        from .find import find_sls
        from .version import installed_tag

        sls = find_sls()
        if sls is not None:
            key["sls_version"] = installed_tag(sls) or ""
    except (ImportError, OSError, ValueError):
        pass
    return key


def validate(manifest: object) -> dict:
    """reject anything that isn't a manifest we understand, before any of it is used"""
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise SlsError("the download-plugin manifest has an unknown schema")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES:
        raise SlsError("the download-plugin manifest has no usable entries")
    for entry in entries:
        if not isinstance(entry, dict):
            raise SlsError("a download-plugin manifest entry isn't an object")
        if entry.get("steam_arch") not in (32, 64, "*"):
            raise SlsError("a download-plugin manifest entry has a bad steam_arch")
        if not isinstance(entry.get("steam_build"), str) or not re.fullmatch(
            r"\d+|\*", entry["steam_build"]
        ):
            raise SlsError("a download-plugin manifest entry has a bad steam_build")
        if not isinstance(entry.get("sls_version"), str):
            raise SlsError("a download-plugin manifest entry has a bad sls_version")
        sha = entry.get("sha256", "")
        if not isinstance(sha, str) or not _HEX64.fullmatch(sha.lower()):
            raise SlsError("a download-plugin manifest entry has a bad sha256")
        entry["sha256"] = sha.lower()
        name = entry.get("file", "")
        if not isinstance(name, str) or Path(name).name != name or name in (".", ".."):
            raise SlsError("a download-plugin manifest entry has a bad file name")
        url = entry.get("url", "")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise SlsError("a download-plugin manifest entry has a bad url")
    extras = manifest.get("plugins")
    if extras is not None:
        if not isinstance(extras, list) or len(extras) > MAX_ENTRIES:
            raise SlsError("the plugin collection has no usable entries")
        for entry in extras:
            if not isinstance(entry, dict):
                raise SlsError("a plugin collection entry isn't an object")
            name = entry.get("name", "")
            if not isinstance(name, str) or not COLLECTION_NAME.fullmatch(name):
                raise SlsError("a plugin collection entry has a bad name")
            if entry.get("steam_arch") not in (32, 64, "*"):
                raise SlsError("a plugin collection entry has a bad steam_arch")
            sha = entry.get("sha256", "")
            if not isinstance(sha, str) or not _HEX64.fullmatch(sha.lower()):
                raise SlsError("a plugin collection entry has a bad sha256")
            entry["sha256"] = sha.lower()
            file_name = entry.get("file", "")
            if not isinstance(file_name, str) or Path(file_name).name != file_name or file_name in (".", ".."):
                raise SlsError("a plugin collection entry has a bad file name")
            url = entry.get("url", "")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise SlsError("a plugin collection entry has a bad url")
            for field in ("version", "desc", "role"):
                if field in entry and not isinstance(entry[field], str):
                    raise SlsError(f"a plugin collection entry has a bad {field}")
    return manifest


def _read_cache() -> dict | None:
    try:
        stamp = MANIFEST_CACHE.stat()
        if time.time() - stamp.st_mtime > MANIFEST_TTL:
            return None
        return validate(json.loads(MANIFEST_CACHE.read_text()))
    except (OSError, ValueError, SlsError):
        return None


def _write_cache(manifest: dict) -> None:
    try:
        MANIFEST_CACHE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        text = json.dumps(manifest, indent=2)
        part = MANIFEST_CACHE.with_suffix(".json.part")
        part.write_text(text)
        part.replace(MANIFEST_CACHE)
    except OSError:
        pass


def load_manifest(refresh: bool = False) -> dict:
    """cached list first, then the repo (and its mirror). offline callers get the cache only"""
    if not refresh:
        cached = _read_cache()
        if cached is not None:
            return cached
    tried = []
    for url in manifest_urls():
        try:
            payload = http.get_json(url, timeout=12)
            if isinstance(payload, dict) and payload.get("encoding") == "base64" and isinstance(
                payload.get("content"), str
            ):
                payload = json.loads(base64.b64decode(payload["content"]))
            manifest = validate(payload)
        except Exception as error:
            tried.append(f"{url}: {error}")
            continue
        _write_cache(manifest)
        return manifest
    cached = _read_cache()
    if cached is not None:
        return cached
    raise SlsError("couldn't load the download-plugin manifest. " + "; ".join(tried))


def _matches_field(entry: dict, field: str, value: str) -> bool:
    spec = entry[field]
    if spec == "*" or spec == value:
        return True
    if field == "sls_version" and value in (entry.get("sls_versions") or []):
        return True
    lo, hi = entry.get(field + "_from"), entry.get(field + "_to")
    if lo is None and hi is None:
        return False
    try:
        number = int(value)
    except ValueError:
        return False
    return (lo is None or number >= int(lo)) and (hi is None or number <= int(hi))


def select(manifest: dict, key: dict) -> tuple[dict, str] | None:
    """pick the closest entry: exact, then explicit ranges, then a declared default"""
    entries = manifest["entries"]
    arch, build, sls = str(key["steam_arch"]), key["steam_build"], key["sls_version"]

    for entry in entries:
        if (
            str(entry["steam_arch"]) == arch
            and entry["steam_build"] == build
            and entry["sls_version"] == sls
        ):
            return entry, "exact"

    for entry in entries:
        if str(entry["steam_arch"]) != arch:
            continue
        if not _matches_field(entry, "steam_build", build) or not _matches_field(entry, "sls_version", sls):
            continue
        if entry["steam_build"] == build and entry["sls_version"] == sls:
            continue  # already handled by the exact pass
        return entry, "range"

    for entry in entries:
        if entry.get("default") is True or (
            entry["steam_arch"] == "*" and entry["steam_build"] == "*" and entry["sls_version"] == "*"
        ):
            return entry, "default"
    return None


def collection(manifest: dict | None = None) -> list[dict]:
    """the optional plugins the public collection offers, in manifest order"""
    return [dict(entry) for entry in (manifest or load_manifest()).get("plugins", [])]


def collection_entry(name: str, arch: int | None = None, manifest: dict | None = None) -> dict | None:
    """one optional plugin by name, preferring the build for this client over a shared one"""
    found = [entry for entry in collection(manifest) if entry["name"].lower() == name.strip().lower()]
    if arch is None:
        return next(iter(found), None)
    for entry in found:
        if str(entry.get("steam_arch")) == str(arch):
            return entry
    return next((entry for entry in found if str(entry.get("steam_arch")) == "*"), None)


def entry_for_bytes(data: bytes, arch: int | None = None) -> dict | None:
    """which checked plugin these bytes are, if the public collection knows them"""
    digest = hashlib.sha256(data).hexdigest()
    try:
        manifest = load_manifest()
    except (SlsError, OSError, ValueError):
        return None
    for entry in (*manifest["entries"], *manifest.get("plugins", [])):
        if entry["sha256"] == digest and (
            arch is None or str(entry.get("steam_arch", "*")) in ("*", str(arch))
        ):
            return entry
    return None


def _plugin_bytes(url: str) -> bytes:
    data = http.get(url, timeout=30, limit=MAX_PLUGIN_BYTES)
    if len(data) > MAX_PLUGIN_BYTES:
        raise SlsError("that download plugin is way bigger than a plugin should be")
    if url.lower().endswith(".zip") or data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                luas = [n for n in archive.namelist() if n.lower().endswith(".lua") and not n.endswith("/")]
                if len(luas) != 1:
                    raise SlsError(f"expected one .lua in the plugin zip, found {len(luas)}")
                data = archive.read(luas[0])
        except zipfile.BadZipFile as error:
            raise SlsError(f"{url}: not a valid zip: {error}") from error
    return data


def fetch(entry: dict) -> bytes:
    """download one entry, unwrap a zip with exactly one lua in it, and check its hash.

    The URL comes from the public manifest entry itself. Bytes are only returned when they match that entry's
    sha256, so a changed collection can't swap a plugin without changing the manifest too.
    """
    urls = [entry["url"]]
    tried = []
    for url in urls:
        try:
            data = _plugin_bytes(url)
            digest = hashlib.sha256(data).hexdigest()
            if digest != entry["sha256"]:
                raise SlsError(f"plugin sha256 was {digest[:12]}, expected {entry['sha256'][:12]}")
            return data
        except Exception as error:
            tried.append(f"{url}: {error}")
    raise SlsError("couldn't fetch the checked download plugin. " + "; ".join(tried))


def matches(data: bytes, entry: dict) -> bool:
    return hashlib.sha256(data).hexdigest() == entry["sha256"]
