from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

from ..util import http
from .errors import SlsError
from .release import download

ARCHIVE_SUFFIXES = (".zip", ".7z")


def _clean(text):
    return text.strip().strip("'\"")


def local_archive(text: str) -> Path | None:
    text = _clean(text)
    if text.startswith("file://"):
        text = urllib.parse.unquote(urllib.parse.urlparse(text).path)
    path = Path(text).expanduser()
    return path if path.is_file() else None


def _repo_url(link):
    scp = re.match(r"^git@([^:]+):(.+)$", link)
    if scp:
        link = f"https://{scp.group(1)}/{scp.group(2)}"
    return link[:-4] if link.endswith(".git") else link


def _split_repo(link):
    parsed = urllib.parse.urlparse(_repo_url(link))
    path = re.split(r"/(?:-|releases|tree|blob|archive|commits?)(?:/|$)", parsed.path.strip("/"))[0]
    parts = [p for p in path.split("/") if p]
    if not parsed.netloc or len(parts) < 2:
        raise SlsError(f"can't find a repo in {link}")
    host = parsed.netloc
    if "gitlab" not in host:
        parts = parts[:2]
    return f"{parsed.scheme or 'https'}://{host}", host, "/".join(parts)


def _release_assets(base, host, repo):
    if host == "github.com":
        rel = http.get_json(f"https://api.github.com/repos/{repo}/releases/latest")
        return rel["tag_name"], [{"name": a["name"], "url": a["browser_download_url"]} for a in rel["assets"]]
    if "gitlab" in host:
        project = urllib.parse.quote(repo, safe="")
        rel = http.get_json(f"{base}/api/v4/projects/{project}/releases/permalink/latest")
        links = rel.get("assets", {}).get("links", [])
        return rel["tag_name"], [{"name": link["name"], "url": link["url"]} for link in links]
    rel = http.get_json(f"{base}/api/v1/repos/{repo}/releases/latest")
    return rel["tag_name"], [{"name": a["name"], "url": a["browser_download_url"]} for a in rel["assets"]]


def _pick(assets):
    ranked = sorted(
        (a for a in assets if a["name"].lower().endswith(ARCHIVE_SUFFIXES)),
        key=lambda a: (
            not a["name"].lower().endswith(".7z"),
            "release" not in a["name"].lower(),
            "source" in a["name"].lower(),
        ),
    )
    return ranked[0] if ranked else None


def _clone_as_zip(link, work_dir):
    if not shutil.which("git"):
        raise SlsError("no release to download and git isn't installed to fetch the source")
    work_dir.mkdir(parents=True, exist_ok=True)
    checkout = work_dir / "paws-private-clone"
    shutil.rmtree(checkout, ignore_errors=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", _repo_url(link), str(checkout)],
        capture_output=True,
        text=True,
        env={"GIT_TERMINAL_PROMPT": "0", "PATH": os.environ.get("PATH", "")},
    )
    if result.returncode != 0:
        raise SlsError(f"git clone failed: {result.stderr.strip()[-200:]}")
    shutil.rmtree(checkout / ".git", ignore_errors=True)
    archive = shutil.make_archive(str(work_dir / "paws-private-source"), "zip", checkout)
    shutil.rmtree(checkout, ignore_errors=True)
    return Path(archive)


def fetch(link: str, work_dir: Path, progress=None) -> tuple[Path, str, bool]:
    """Turn what was pasted or dropped into an archive on disk: (archive, name, delete_afterwards)."""
    link = _clean(link)
    local = local_archive(link)
    if local is not None:
        return local, local.stem, False
    if not re.match(r"^(https?://|git@)", link):
        raise SlsError(f"not a file or a repo link: {link}")
    if link.split("?")[0].lower().endswith(ARCHIVE_SUFFIXES):
        return download(link, work_dir, progress), "private", True
    base, host, repo = _split_repo(link)
    try:
        tag, assets = _release_assets(base, host, repo)
        asset = _pick(assets)
    except (urllib.error.URLError, KeyError, ValueError):
        tag, asset = "source", None
    if asset is not None:
        return download(asset["url"], work_dir, progress), tag, True
    return _clone_as_zip(link, work_dir), "source", True
