from __future__ import annotations

import os

DEFAULT_URL = "https://github.com/one-eyed-queen/paw"
BRANCH = "main"


def repo_url() -> str:
    return os.environ.get("PAWS_UPDATE_URL") or DEFAULT_URL


def repo_branch() -> str:
    return os.environ.get("PAWS_UPDATE_BRANCH") or BRANCH


def short_name(url: str | None = None) -> str:
    u = (url or repo_url()).removesuffix(".git")
    for prefix in ("https://", "http://", "git@", "ssh://"):
        u = u.removeprefix(prefix)
    return u.replace("github.com:", "github.com/")
