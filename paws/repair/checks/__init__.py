from __future__ import annotations

from ...config.where import find_config
from ...util import backup
from ..model import Problem
from ._shared import move_aside
from .api_pipe import check_api_pipe
from .apps import check_additional_apps, check_additional_packages
from .config import (
    check_config_broken,
    check_config_dupes,
    check_config_encoding,
    check_config_keys,
    check_config_missing,
    check_config_permissions,
    check_config_values,
    find_duplicates,
)
from .launchers import STEAM_LAUNCHERS, USER_APPS, audit_paths, check_launchers, strip_ld_audit
from .paws_files import check_journal, check_settings, check_tickets

__all__ = [
    "Problem",
    "move_aside",
    "find_duplicates",
    "check_config_missing",
    "check_config_broken",
    "check_config_keys",
    "check_config_dupes",
    "check_config_encoding",
    "check_config_permissions",
    "check_config_values",
    "check_api_pipe",
    "check_additional_apps",
    "check_additional_packages",
    "USER_APPS",
    "STEAM_LAUNCHERS",
    "audit_paths",
    "strip_ld_audit",
    "check_launchers",
    "check_settings",
    "check_journal",
    "check_tickets",
    "scan",
]


def config_errors(config_path, online=False):
    dupes = check_config_dupes(config_path)
    structural = check_config_broken(config_path) + check_config_encoding(config_path) + dupes
    return structural, check_config_values(config_path, online)


def refresh_known_good():
    """a config that reads clean is what paws falls back to. edited by hand, or by paws, it counts the same"""
    config_path = find_config()
    if config_path is None:
        return False
    structural, values = config_errors(config_path)
    if structural or any(p.severity == "error" for p in values):
        return False
    backup.snapshot_good(config_path)
    return True


def scan(online: bool = False) -> list[Problem]:
    out = []
    out += check_config_missing()
    config_path = find_config()
    if config_path is not None:
        structural, values = config_errors(config_path, online)
        out += structural + values
        out += check_config_keys(config_path)
        out += check_config_permissions(config_path)
        out += check_additional_apps(config_path)
        if online:  # asks the store about every package, so only for `paws fix`
            out += check_additional_packages(config_path)
        if not structural and not any(p.severity == "error" for p in values):
            backup.snapshot_good(config_path)
    out += check_api_pipe()
    out += check_launchers()
    out += check_tickets()
    out += check_settings()
    out += check_journal()
    return out
