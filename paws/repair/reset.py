from __future__ import annotations

from ..config import default_config_text, upstream
from ..config.heal import yaml_ok
from ..config.io import write_now
from ..config.where import find_config
from ..paths import default_config_dir
from ..sls.find import find_sls
from ..sls.tickets import list_tickets
from ..util import backup


def latest_config_text():
    """the newest config SLSsteam ships: github first, then the copy that came with the install, then ours"""
    text = upstream.fetch_github_text()
    if text and yaml_ok(text):
        return text, "github"
    sls = find_sls()
    template = sls.lib_dir / "res" / "config.yaml" if sls and sls.lib_dir else None
    if template is not None and template.is_file():
        text = template.read_text(errors="replace")
        if yaml_ok(text):
            return text, "your SLSsteam install"
    return default_config_text(), "paws' own copy"


def reset_config():
    path = find_config() or default_config_dir() / "config.yaml"
    text, source = latest_config_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = backup.backup_file(path)
    write_now(path, text if text.endswith("\n") else text + "\n")
    return f"config is back to the latest one from {source}" + (
        f", the old one is in the backups ({kept})" if kept else ""
    )


def clear_tickets():
    tickets = list_tickets()
    for ticket in tickets:
        backup.backup_file(ticket.path)
        ticket.path.unlink(missing_ok=True)
    return f"cleared {len(tickets)} ticket(s), copies are in the backups" if tickets else "no tickets to clear"
