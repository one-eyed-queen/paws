from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..paths import default_config_dir
from ..sls.model import SlsInstall
from ..util import http
from .model import SteamInstall

UPDATES_URLS = (
    "https://raw.githubusercontent.com/AceSLS/SLSsteam/refs/heads/main/res/updates.yaml",
    "https://cdn.jsdelivr.net/gh/AceSLS/SLSsteam/res/updates.yaml",
)


CLIENT_DIRS = ("ubuntu12_32", "ubuntu32_32")


_TAG_RE = re.compile(r"\d{14}")


@dataclass
class ClientCheck:
    path: Path | None = None
    sha256: str | None = None
    listed_for: list[str] = field(default_factory=list)
    installed_tag: str | None = None
    latest_tag: str | None = None
    known_tags: list[str] = field(default_factory=list)
    source: str = ""
    error: str = ""

    @property
    def ok_for_installed(self) -> bool | None:
        if not self.sha256 or not self.installed_tag or not self.known_tags:
            return None
        return self.installed_tag in self.listed_for

    @property
    def ok_for_latest(self) -> bool | None:
        if not self.sha256 or not self.latest_tag or not self.known_tags:
            return None
        return self.latest_tag in self.listed_for


def client_path(steam: SteamInstall | None) -> Path | None:
    if steam is None or steam.root is None:
        return None
    for d in CLIENT_DIRS:
        p = steam.root / d / "steamclient.so"
        if p.exists():
            return p
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_updates(text: str) -> dict[str, set[str]]:
    try:
        data = yaml.safe_load(text)
        hashes = data["SafeModeHashes"]
        return {str(tag): {str(h).lower() for h in (vals or [])} for tag, vals in hashes.items()}
    except (yaml.YAMLError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"not a SafeModeHashes file: {error}") from error


def load_updates(
    sls: SlsInstall | None, *, network: bool = True, timeout: float = 6.0
) -> tuple[dict[str, set[str]], str]:
    local = []
    if sls is not None and sls.lib_dir is not None:
        local.append(("installed release", sls.lib_dir / "res" / "updates.yaml"))
    local.append(("SLSsteam cache", default_config_dir() / ".updates.yaml"))
    for label, path in local:
        try:
            return parse_updates(path.read_text()), label
        except (OSError, ValueError):
            continue
    if network:
        for url in UPDATES_URLS:
            try:
                return parse_updates(http.get_text(url, timeout=timeout)), "github"
            except (OSError, ValueError):
                continue
    return {}, ""


def check_client(
    steam: SteamInstall | None,
    sls: SlsInstall | None,
    latest_tag: str | None = None,
    installed_tag: str | None = None,
    *,
    network: bool = True,
) -> ClientCheck:
    result = ClientCheck(installed_tag=installed_tag, latest_tag=latest_tag)
    path = client_path(steam)
    if path is None:
        result.error = "no steamclient.so found under the Steam root"
        return result
    result.path = path
    try:
        result.sha256 = sha256_file(path)
    except OSError as error:
        result.error = f"can't read {path.name}: {error}"
        return result
    updates, result.source = load_updates(sls, network=network)
    result.known_tags = sorted(updates)
    result.listed_for = sorted(tag for tag, hashes in updates.items() if result.sha256 in hashes)
    if not result.latest_tag and result.known_tags:
        result.latest_tag = result.known_tags[-1]
    return result
