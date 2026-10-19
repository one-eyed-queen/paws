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
    # which of the four assets SLSsteam publishes: a portable "Any" .7z or a native "Arch"
    # .pkg.tar.zst, each in a release or a debug flavour. left unset means "whatever's newest"
    variant: str = "any"
    flavour: str = "release"

    def describe(self) -> str:
        if self.kind == "github":
            return f"GitHub release {self.tag or 'latest'} ({self.variant}/{self.flavour})"
        if self.kind == "private":
            return f"Private {self.name} build {self.url}"
        if self.kind == "forgejo":
            return "Forgejo mirror latest"
        if self.kind == "local":
            return f"Local file {self.url}"
        return self.name


def _flavour_of(name: str) -> str:
    """release / debug / release.

    an asset with no flavour word in its name is the plain build, which is what "release" was
    called before the split existed - SLSsteam.7z and SLSsteam-Arch.pkg.tar.zst are release
    builds, so treating them as "unknown" made a release request pick the debug asset instead.
    """
    lowered = name.lower()
    if "debug" in lowered:
        return "debug"
    return "release"


@dataclass
class SlsRelease:
    tag: str
    date: str
    assets: list[dict] = field(default_factory=list)
    note: str = ""

    def available(self) -> dict:
        """what this release actually offers: {"variant": ("release", "debug"), ...} so the ui can
        grey out choices a release doesn't have instead of picking and failing"""
        out: dict[str, set] = {}
        for asset in self.assets or []:
            name = asset["name"].lower()
            variant = "arch" if "-arch" in name else "any"
            out.setdefault(variant, set()).add(_flavour_of(name))
        return {k: tuple(sorted(v)) for k, v in out.items()}

    def pick_asset(self, variant: str = "any", flavour: str = "release") -> dict | None:
        """choose one asset out of the four SLSsteam publishes:

            SLSsteam-Any-release.7z                  portable, works on any distro
            SLSsteam-Any-debug.7z                    portable, debug build
            SLSsteam-Arch-release-x86_64.pkg.tar.zst native arch package
            SLSsteam-Arch-debug-x86_64.pkg.tar.zst   native arch package, debug

        the flavour split only exists from around aug 2026 - older releases shipped a plain
        SLSsteam-Any.7z with nothing to choose between. those still resolve, just without the
        choice, rather than failing.

        picks by score rather than by filter order, so adding another flavour later can't silently
        change which one wins.
        """
        want_variant = variant if variant in ("any", "arch") else "any"
        want_flavour = flavour if flavour in ("release", "debug") else "release"
        best, best_score = None, None
        for asset in self.assets or []:
            name = asset["name"].lower()
            is_7z = name.endswith(".7z")
            # the portable build used to be just SLSsteam.7z, before "Any" was spelled out. a .7z
            # that isn't an arch package is an "any" asset either way
            has_variant = want_variant in name or (want_variant == "any" and is_7z)
            got_flavour = _flavour_of(name)
            if want_variant == "arch" and not has_variant:
                continue
            # lower is better. a build that actually carries the flavour asked for beats the
            # plain one, which is why SLSsteam.7z has to count as the release build
            score = (not has_variant, got_flavour != want_flavour)
            if best_score is None or score < best_score:
                best, best_score = asset, score
        if best is not None:
            return best
        for asset in self.assets or []:  # nothing matched at all - take any 7z rather than fail
            if asset["name"].lower().endswith(".7z"):
                return asset
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


def resolve_source(source: SlsSource) -> tuple[str, str, str | None]:
    """-> (url, asset name, release tag).

    the tag comes back because it is the only comparable build id - the asset name has no digits in
    it, so an install done by paws could never be checked against github's newest tag and always
    read as "somewhere else, can't tell". returning it here means the caller records the tag of the
    release it actually downloaded, with no second api call.
    """
    if source.kind == "github":
        rels = {r.tag: r for r in github_releases(limit=60)}
        if source.tag:
            rel = rels.get(source.tag)
            if not rel:
                raise SlsError(f"release tag {source.tag} not found")
        else:
            rel = rels.get(max(rels.keys()))
            if not rel:
                raise SlsError("no releases found on GitHub")
        asset = (
            source.asset_name
            and next((a for a in rel.assets if a["name"] == source.asset_name), None)
            or rel.pick_asset(source.variant, source.flavour)
        )
        if not asset:
            raise SlsError(
                f"no {source.variant}/{source.flavour} asset in release {rel.tag} "
                f"(it has: {', '.join(a['name'] for a in rel.assets) or 'nothing'})"
            )
        return asset["url"], asset["name"], rel.tag
    if source.kind == "forgejo":
        with urllib.request.urlopen(FORGEJO_API, timeout=20) as r:
            rel = json.loads(r.read().decode())
        for a in rel.get("assets", []):
            if a["name"].lower().endswith(".7z"):
                return a["browser_download_url"], rel.get("tag_name", "forgejo-latest"), rel.get("tag_name")
        raise SlsError("no .7z asset in the forgejo mirror latest release")
    if source.kind in ("private", "local"):
        if not source.url:
            raise SlsError(f"{source.kind} source needs a url")
        return source.url, source.name, None
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
