from __future__ import annotations

from . import headcrab, plugins
from .activation import DEFAULT_TIMEOUT, activate, ensure_subscribed
from .api import API_PATH, write_api_command
from .archive import extract_archive
from .desktop import write_launcher
from .errors import SlsError
from .find import SYSTEM_APPS_DIR, SYSTEM_LIB_DIRS, find_sls
from .install import install_port, install_release, merge_user_config, update_port
from .model import SlsInstall
from .release import (
    FORGEJO_API,
    GITHUB_API,
    SlsRelease,
    SlsSource,
    download,
    github_releases,
    resolve_source,
)
from .tickets import (
    Ticket,
    cache_dir,
    delete_ticket,
    list_tickets,
    load_ticket_file,
    make_ticket_file,
    save_ticket,
    to_clipboard_text,
    validate_payload,
)
from .uninstall import paws_owns, uninstall
from .version import (
    _LATEST_CACHE,
    ABSENT,
    NO,
    UNKNOWN,
    YES,
    fetch_latest_github_tag,
    installed_tag,
    installed_version,
    update_available,
    update_reason,
    update_state,
)

__all__ = [
    "ABSENT",
    "API_PATH",
    "DEFAULT_TIMEOUT",
    "FORGEJO_API",
    "GITHUB_API",
    "NO",
    "SYSTEM_APPS_DIR",
    "SYSTEM_LIB_DIRS",
    "UNKNOWN",
    "YES",
    "_LATEST_CACHE",
    "SlsError",
    "SlsInstall",
    "SlsRelease",
    "SlsSource",
    "Ticket",
    "activate",
    "cache_dir",
    "delete_ticket",
    "download",
    "ensure_subscribed",
    "extract_archive",
    "fetch_latest_github_tag",
    "find_sls",
    "github_releases",
    "headcrab",
    "install_port",
    "install_release",
    "installed_tag",
    "installed_version",
    "list_tickets",
    "load_ticket_file",
    "make_ticket_file",
    "merge_user_config",
    "paws_owns",
    "plugins",
    "resolve_source",
    "save_ticket",
    "to_clipboard_text",
    "uninstall",
    "update_available",
    "update_port",
    "update_reason",
    "update_state",
    "validate_payload",
    "write_api_command",
    "write_launcher",
]
