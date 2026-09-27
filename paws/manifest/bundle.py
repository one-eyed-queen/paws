from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ..paths import HOME
from .lua import LuaManifest


class ManifestBundle:
    def __init__(self, appid: int | None = None):
        self.appid: int | None = appid
        self.luas: list[LuaManifest] = []
        self.manifests: list[tuple[int, int, Path]] = []
        self.keys: list[tuple[int, str]] = []
        self.names: dict[int, str] = {}

    def add_key_file(self, path: Path):
        if path.suffix.lower() == ".key":
            content = path.read_text(errors="replace").strip().strip('"')
            m = re.fullmatch(r"[0-9a-fA-F]{32,}", content)
            if m:
                self.keys.append((self.appid or 0, content))

    def add_manifest_file(self, path: Path):
        if path.suffix.lower() != ".manifest":
            return
        m = re.search(r"(?:manifest_)?(\d+)_(\d+)\.manifest$", path.name, re.IGNORECASE)
        if m:
            self.manifests.append((int(m.group(1)), int(m.group(2)), path))

    def add_lua_file(self, path: Path):
        if path.suffix.lower() == ".lua":
            lm = LuaManifest(path)
            lm.parse()
            self.luas.append(lm)

    def add_file(self, path: Path):
        sfx = path.suffix.lower()
        if sfx == ".lua":
            self.add_lua_file(path)
        elif sfx == ".manifest":
            self.add_manifest_file(path)
        elif sfx == ".key":
            self.add_key_file(path)

    def add_archive(self, zip_path: Path, workdir: Path):
        with zipfile.ZipFile(zip_path) as z:
            matched = []
            for info in z.infolist():
                nm = Path(info.filename)
                if nm.suffix.lower() in (".lua", ".manifest", ".key"):
                    matched.append(nm)
            if not matched:
                return
            extract_root = workdir / f"unz-{zip_path.stem}"
            for nm in matched:
                z.extract(str(nm), extract_root)
                self.add_file(extract_root / nm)

    def flatten(self):
        depots = {}
        for lm in self.luas:
            for depot, key, _ in lm.decryption_keys:
                depots[depot] = key
        for depot, key in self.keys:
            depots.setdefault(depot, key)
        app_ids = set()
        for lm in self.luas:
            app_ids.update(a for a, _ in lm.app_ids)
        return {
            "depots": depots,
            "app_ids": sorted(app_ids),
            "manifests": self.manifests,
            "names": self.names,
        }


def parse_key_text(content: str, appid: int) -> dict:
    content = content.strip().strip('"')
    key = (
        content.split()[-1]
        if re.fullmatch(r"[0-9a-fA-F]{32,}", content)
        else (content if re.fullmatch(r"[0-9a-fA-F]{32,}", content) else None)
    )
    return {"depots": {appid: key} if key else {}, "app_ids": [], "manifests": [], "names": {}}


def load_bundle(path: Path) -> ManifestBundle:
    bundle = ManifestBundle()
    if path.suffix.lower() == ".zip":
        bundle.add_archive(path, HOME / ".cache/paws")
    else:
        bundle.add_file(path)
    return bundle


def parse_lua_text(content: str) -> dict:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as tf:
        tf.write(content)
        temporary_path = Path(tf.name)
    try:
        b = ManifestBundle()
        b.add_lua_file(temporary_path)
        return b.flatten()
    finally:
        temporary_path.unlink(missing_ok=True)
