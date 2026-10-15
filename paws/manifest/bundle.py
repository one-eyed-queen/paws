from __future__ import annotations

import re
from pathlib import Path

from ..paths import HOME
from .lua import LuaManifest


class ManifestBundle:
    def __init__(self, appid: int | None = None):
        self.appid: int | None = appid
        self.luas: list[LuaManifest] = []
        self.manifests: list[tuple[int, int, Path]] = []
        self.keys: list[tuple[int, str]] = []
        self.orphan_keys: list[str] = []
        self.names: dict[int, str] = {}

    def add_key_file(self, path: Path):
        if path.suffix.lower() == ".key":
            content = path.read_text(errors="replace").strip().strip('"')
            m = re.fullmatch(r"[0-9a-fA-F]{32,}", content)
            # a .key file is just a bare hex string - it carries no depot id of its own, so it
            # can't be filed yet. flatten() pairs it with the single depot that still needs a
            # key. writing it under the game's appid (or under depot 0, as this used to) puts a
            # decryption key against a depot that doesn't exist
            if m:
                self.orphan_keys.append(content)

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

    def add_archive(self, archive_path: Path, workdir: Path):
        # .zip, .7z and the tarballs all show up in the wild for these bundles; reuse the same
        # extractor sls/archive.py already relies on (py7zr, zstandard, falling back to a
        # system 7z or zstd binary)
        from ..sls.archive import extract_archive

        extract_root = workdir / f"unz-{archive_path.stem}"
        extract_archive(archive_path, extract_root)
        # community bundles are often named after the game's own appid (e.g. "620.zip") - use it
        # as the appid so the store lookup and the plan have something to work with. never
        # overrides an appid already given explicitly (e.g. one typed in the search box)
        if self.appid is None and archive_path.stem.isdigit():
            self.appid = int(archive_path.stem)
        for path in sorted(extract_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in (".lua", ".manifest", ".key"):
                self.add_file(path)

    def flatten(self):
        depots = self._depots_from_luas()
        # pair up whatever .key files came in on their own. they're only usable when exactly one
        # depot still needs a key - with more than one candidate, guessing would attach the key
        # to the wrong depot, so it stays out and gets reported instead. unpaired_keys() re-runs
        # this to say which ones those were
        self._pair_orphan_keys(depots)
        app_ids = set()
        for lm in self.luas:
            app_ids.update(a for a, _ in lm.app_ids)
            # the trailing comment on an AddAppID() line is usually the game's real name
            for app_id, comment in lm.app_ids:
                if comment:
                    self.names.setdefault(app_id, comment)
            for depot, name in lm.dlc_names.items():
                if name:
                    self.names.setdefault(depot, name)
        return {
            "depots": depots,
            "app_ids": sorted(app_ids),
            "manifests": self.manifests,
            "names": self.names,
        }

    def _pair_orphan_keys(self, depots: dict) -> list[str]:
        leftovers = []
        for key in self.orphan_keys:
            missing = [d for d in sorted(self.known_depots()) if d not in depots]
            if len(missing) == 1:
                depots[missing[0]] = key
            else:
                leftovers.append(key)
        return leftovers

    def _depots_from_luas(self) -> dict:
        depots = {}
        for lm in self.luas:
            for depot, key, _ in lm.decryption_keys:
                depots[depot] = key
        for depot, key in self.keys:
            depots.setdefault(depot, key)
        return depots

    def unpaired_keys(self) -> list[str]:
        """orphan .key files we could not attach to a depot - these never reach the config.
        mirrors flatten() exactly so the warning never contradicts what actually got written"""
        return self._pair_orphan_keys(self._depots_from_luas())

    def known_depots(self) -> set[int]:
        """every depot id seen anywhere: from setManifestid(), from a standalone .manifest
        filename, or from an AddAppID() that carries a decryption key"""
        depots = {d for lm in self.luas for d, _, _ in lm.manifest_ids}
        depots |= {d for d, _, _p in self.manifests}
        depots |= {d for lm in self.luas for d, _, _ in lm.decryption_keys}
        return depots


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
    from ..sls.archive import is_archive

    if is_archive(path):
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
