from __future__ import annotations

from .activation import DEFAULT_TIMEOUT, activate, ensure_subscribed
from .api import API_PATH, write_api_command
from .archive import extract_archive
from .desktop import write_launcher
from .errors import SlsError
from . import headcrab
from .find import SYSTEM_APPS_DIR, SYSTEM_LIB_DIRS, find_sls
from . import plugins
from .install import merge_user_config, install_release
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
    fetch_latest_github_tag,
    installed_tag,
    installed_version,
    update_available,
)

__all__ = [
    "headcrab",
    "plugins",
    "DEFAULT_TIMEOUT",
    "ensure_subscribed",
    "activate",
    "API_PATH",
    "write_api_command",
    "extract_archive",
    "write_launcher",
    "SlsError",
    "SYSTEM_LIB_DIRS",
    "SYSTEM_APPS_DIR",
    "find_sls",
    "merge_user_config",
    "install_release",
    "SlsInstall",
    "GITHUB_API",
    "FORGEJO_API",
    "SlsSource",
    "SlsRelease",
    "github_releases",
    "resolve_source",
    "download",
    "Ticket",
    "cache_dir",
    "list_tickets",
    "load_ticket_file",
    "validate_payload",
    "save_ticket",
    "make_ticket_file",
    "delete_ticket",
    "to_clipboard_text",
    "paws_owns",
    "uninstall",
    "installed_version",
    "installed_tag",
    "update_available",
    "_LATEST_CACHE",
    "fetch_latest_github_tag",
]
