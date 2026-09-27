from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .errors import SlsError

GITHUB_API = "https://api.github.com/repos/AceSLS/SLSsteam"


FORGEJO_API = "https://forgejo.servergamer.win/api/v1/repos/Parasitic_Hollow/Hollow-Steam/releases/latest"


@dataclass
class SlsSource:
    name: str
    kind: str
    url: str | None = None
    tag: str | None = None
    asset_name: str | None = None

    def describe(self) -> str:
        if self.kind == "github":
            return f"GitHub release {self.tag or 'latest'}"
        if self.kind == "private":
            return f"Private {self.name} build {self.url}"
        if self.kind == "forgejo":
            return "Forgejo mirror latest"
        if self.kind == "local":
            return f"Local file {self.url}"
        return self.name


@dataclass
class SlsRelease:
    tag: str
    date: str
    assets: list[dict] = field(default_factory=list)
    note: str = ""

    def pick_asset(self) -> dict | None:
        for a in self.assets:
            n = a["name"].lower()
            if "release" in n and n.endswith(".7z"):
                return a
        for a in self.assets:
            n = a["name"].lower()
            if n.endswith(".7z"):
                return a
        return None


def github_releases(limit: int = 30, timeout: float = 20) -> list[SlsRelease]:
    with urllib.request.urlopen(f"{GITHUB_API}/releases?per_page={limit}", timeout=timeout) as r:
        data = json.loads(r.read().decode())
    out = []
    for rel in data:
        assets = [
            {"name": a["name"], "url": a["browser_download_url"], "size": a.get("size", 0)}
            for a in rel.get("assets", [])
        ]
        out.append(
            SlsRelease(tag=rel["tag_name"], date=rel.get("published_at", ""), assets=assets, note=rel.get("body") or "")
        )
    return out


def resolve_source(source: SlsSource) -> tuple[str, str]:
    if source.kind == "github":
        rels = {r.tag: r for r in github_releases(limit=60)}
        if source.tag:
            rel = rels.get(source.tag)
            if not rel:
                raise SlsError(f"release tag {source.tag} not found")
        else:
            rel = rels.get(sorted(rels.keys())[-1])
            if not rel:
                raise SlsError("no releases found on GitHub")
        asset = (
            source.asset_name
            and next((a for a in rel.assets if a["name"] == source.asset_name), None)
            or rel.pick_asset()
        )
        if not asset:
            raise SlsError(f"no .7z asset in release {rel.tag}")
        return asset["url"], f"{rel.tag}"
    if source.kind == "forgejo":
        with urllib.request.urlopen(FORGEJO_API, timeout=20) as r:
            rel = json.loads(r.read().decode())
        for a in rel.get("assets", []):
            if a["name"].lower().endswith(".7z"):
                return a["browser_download_url"], rel.get("tag_name", "forgejo-latest")
        raise SlsError("no .7z asset in the forgejo mirror latest release")
    if source.kind in ("private", "local"):
        if not source.url:
            raise SlsError(f"{source.kind} source needs a url")
        return source.url, source.name
    raise SlsError(f"unknown source kind {source.kind}")


def download(url: str, dest_dir: Path, progress=None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = url.split("?")[0].rsplit("/", 1)[-1] or "slssteam.7z"
    target = dest_dir / name
    request = urllib.request.Request(url, headers={"User-Agent": "paws/0.1"})
    with urllib.request.urlopen(request, timeout=60) as r, open(target, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    return target
