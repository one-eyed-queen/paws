from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import git, state
from .checkout import find_checkout
from .install import reinstall
from .repo import repo_branch, repo_url


@dataclass
class Status:
    state: str
    message: str
    local: str | None = None
    remote: str | None = None
    behind: int = 0
    subjects: list[str] = field(default_factory=list)
    checkout: Path | None = None

    @property
    def can_apply(self) -> bool:
        return self.state == "behind"


def check(url: str | None = None, branch: str | None = None, checkout: Path | None = None) -> Status:
    url, branch = url or repo_url(), branch or repo_branch()
    checkout = checkout or find_checkout()
    if checkout is None:
        return Status("unmanaged", "not a git checkout, so it can't update itself (use your package manager)")
    try:
        local = git.head(checkout)
    except git.GitError as error:
        return Status("error", f"couldn't read the local build: {error}", checkout=checkout)
    try:
        remote = git.fetch(checkout, url, branch)
    except git.GitError as error:
        return Status("offline", f"couldn't reach the repo ({error})", local=local, checkout=checkout)
    try:
        behind = git.count_behind(checkout, remote)
        if behind == 0:
            return Status("current", "up to date", local=local, remote=remote, checkout=checkout)
        subs = git.subjects(checkout, remote)
        if not git.can_fast_forward(checkout, remote):
            return Status(
                "blocked",
                f"{behind} new, but this checkout has commits of its own",
                local,
                remote,
                behind,
                subs,
                checkout,
            )
        if git.is_dirty(checkout):
            return Status(
                "blocked", f"{behind} new, but this checkout has local changes", local, remote, behind, subs, checkout
            )
    except git.GitError as error:
        return Status(
            "error", f"couldn't compare with the repo: {error}", local=local, remote=remote, checkout=checkout
        )
    return Status("behind", f"{behind} new commit{'s' if behind != 1 else ''}", local, remote, behind, subs, checkout)


def apply(status: Status, installer: Callable[[Path], tuple[bool, str]] = reinstall) -> Status:
    if not status.can_apply or status.checkout is None or status.remote is None:
        return status
    co = status.checkout
    try:
        git.fast_forward(co, status.remote)
    except git.GitError as error:
        return Status("error", f"pull failed: {error}", status.local, status.remote, status.behind, status.subjects, co)
    ok, why = installer(co)
    if not ok:
        try:
            git._run(["reset", "--hard", "--quiet", status.local], co, timeout=30.0)
        except git.GitError:
            pass
        return Status(
            "error",
            f"install failed, rolled back ({why})",
            status.local,
            status.remote,
            status.behind,
            status.subjects,
            co,
        )
    state.save(installed=status.remote)
    return Status(
        "updated",
        f"updated to {git.short(status.remote)}",
        status.local,
        status.remote,
        status.behind,
        status.subjects,
        co,
    )


def record(status: Status):
    state.save(checked_at=time.time(), state=status.state, remote=status.remote, local=status.local)
