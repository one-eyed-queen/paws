from __future__ import annotations

from .repo import DEFAULT_URL, repo_branch, repo_url

__all__ = ["DEFAULT_URL", "Status", "apply", "check", "enabled", "force", "repo_branch", "repo_url", "run"]


def __getattr__(name: str):
    # imported on first use, so the loading screen isn't waiting on what it's there to cover
    if name in ("enabled", "run"):
        from . import startup

        return getattr(startup, name)
    if name in ("Status", "apply", "check", "force"):
        from . import status

        return getattr(status, name)
    raise AttributeError(name)
