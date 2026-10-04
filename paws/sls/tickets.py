from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..paths import HOME, default_config_dir
from ..windows import IS_WINDOWS
from .find import find_sls


@dataclass
class Ticket:
    appid: str
    encrypted: bool
    steam_id: str
    payload: str
    path: Path | None = None

    @property
    def key(self) -> str:
        return "encryptedTicket" if self.encrypted else "ticket"

    @property
    def filename(self) -> str:
        return f"{'encryptedTicket' if self.encrypted else 'ticket'}_{self.appid}.yaml"

    @property
    def base(self) -> str:
        return self.filename

    @property
    def size(self) -> int:
        if self.path and self.path.exists():
            return self.path.stat().st_size
        return len(self.payload)

    def to_yaml(self) -> str:
        return f"steamId: {self.steam_id}\n{self.key}: {self.payload}\n"


def _fallback_cache() -> Path:
    return default_config_dir() / "cache" if IS_WINDOWS else HOME / ".config/SLSsteam/cache"


def cache_dir() -> Path | None:
    sls = find_sls()
    if sls and sls.cache:
        return Path(sls.cache)
    d = _fallback_cache()
    return d if d.exists() else None


def list_tickets() -> list[Ticket]:
    d = cache_dir()
    out = []
    if not d:
        return out
    for f in d.glob("*.yaml"):
        t = load_ticket_file(f)
        if t:
            out.append(t)
    return sorted(out, key=lambda t: (not t.encrypted, int(t.appid)))


def load_ticket_file(path: Path) -> Ticket | None:
    m = re.search(r"(ticket|encryptedTicket)_(\d+)\.yaml$", path.name)
    if not m:
        return None
    encrypted = m.group(1) == "encryptedTicket"
    appid = m.group(2)
    key = "encryptedTicket" if encrypted else "ticket"
    try:
        text = path.read_text()
        steam_id = _val(text, "steamId")
        payload = _val(text, key)
    except OSError:
        return None
    if not steam_id or not payload:
        return None
    return Ticket(appid=appid, encrypted=encrypted, steam_id=steam_id, payload=payload, path=path)


def _val(text, k):
    m = re.search(rf"^\s*{k}:\s*(\S+)", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def validate_payload(payload: str) -> bool:
    p = payload.strip()
    return bool(re.fullmatch(r"[A-Za-z0-9+/=]+", p)) and len(p) % 4 == 0


def _ensure_cache_dir():
    d = cache_dir() or _fallback_cache()
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_ticket(appid: str, yaml_text: str, backup: bool = True) -> Ticket:
    text = yaml_text.strip()
    steam_id = _val(text, "steamId")
    payload = _val(text, "ticket") or _val(text, "encryptedTicket")
    encrypted = "encryptedTicket" in text
    if not (steam_id and payload and validate_payload(payload)):
        raise ValueError("that isn't a ticket: it needs steamId and a ticket or encryptedTicket in base64")

    d = _ensure_cache_dir()
    from ..util.backup import backup_file

    t = Ticket(appid=str(appid), encrypted=encrypted, steam_id=steam_id, payload=payload)
    dst = d / t.filename
    if backup and dst.exists():
        backup_file(dst)
    dst.write_text(t.to_yaml())
    t.path = dst
    return t


def make_ticket_file(appid: str, steam_id: str, payload: str, encrypted: bool, backup: bool = True) -> Ticket:
    if not validate_payload(payload):
        raise ValueError("the ticket part isn't valid base64")
    d = _ensure_cache_dir()
    from ..util.backup import backup_file

    t = Ticket(appid=str(appid), encrypted=encrypted, steam_id=steam_id, payload=payload)
    dst = d / t.filename
    if backup and dst.exists():
        backup_file(dst)
    dst.write_text(t.to_yaml())
    t.path = dst
    return t


def delete_ticket(t: Ticket) -> bool:
    if t.path and t.path.exists():
        t.path.unlink()
        return True
    return False


def to_clipboard_text(t: Ticket) -> str:
    return t.to_yaml()
