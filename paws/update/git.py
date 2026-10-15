from __future__ import annotations

import os
import subprocess
from pathlib import Path

FETCH_TIMEOUT = 10.0


class GitError(Exception):
    pass


def _run(args, cwd, timeout=8.0):
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "true",
        "GCM_INTERACTIVE": "never",
        "LC_ALL": "C",
    }
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise GitError("git isn't installed") from error
    except subprocess.TimeoutExpired as error:
        raise GitError("timed out") from error
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or [f"git {args[0]} failed"])[-1]
        raise GitError(last)
    return r.stdout.strip()


def is_repo(path: Path) -> bool:
    try:
        return _run(["rev-parse", "--is-inside-work-tree"], path) == "true"
    except GitError:
        return False


def head(path: Path) -> str:
    return _run(["rev-parse", "HEAD"], path)


def short(sha: str | None) -> str:
    return (sha or "")[:7] or "unknown"


def is_dirty(path: Path) -> bool:
    return bool(_run(["status", "--porcelain", "--untracked-files=no"], path))


def fetch(path: Path, url: str, branch: str) -> str:
    _run(["fetch", "--quiet", url, branch], path, timeout=FETCH_TIMEOUT)
    return _run(["rev-parse", "FETCH_HEAD"], path)


def count_behind(path: Path, tip: str) -> int:
    return int(_run(["rev-list", "--count", f"HEAD..{tip}"], path))


def can_fast_forward(path: Path, tip: str) -> bool:
    try:
        _run(["merge-base", "--is-ancestor", "HEAD", tip], path)
        return True
    except GitError:
        return False


def subjects(path: Path, tip: str, limit: int = 5) -> list[str]:
    out = _run(["log", f"--max-count={limit}", "--format=%s", f"HEAD..{tip}"], path)
    return [line for line in out.splitlines() if line]


def fast_forward(path: Path, tip: str):
    _run(["merge", "--ff-only", "--quiet", tip], path, timeout=30.0)


def hard_reset(path: Path, tip: str):
    """throw the working tree away and put it exactly on tip. this is what --force means, and it
    is the only way past a checkout that has local edits or its own commits: everything in the
    working tree is discarded, tracked and untracked alike"""
    _run(["reset", "--hard", "--quiet", tip], path, timeout=60.0)


def stash(path: Path) -> str | None:
    """put local changes aside instead of deleting them, so a forced update can be undone by hand.
    returns the stash ref, or None when there was nothing to stash"""
    try:
        out = _run(
            ["stash", "push", "--quiet", "--include-untracked", "-m", "paws: before --force update"], path, timeout=60.0
        )
    except GitError:
        return None
    return out or "stash@{0}"
