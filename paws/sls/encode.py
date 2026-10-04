from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .tickets import Ticket, list_tickets, validate_payload

MAGIC_ENC = "paws1e."
MAGIC_LEGACY = "paws1."
_HEADER = b"paws1\x02"
_VERSION = 2
BIND_NS = uuid.NAMESPACE_URL
_RECOGNISED = ("encryptedTicket", "ticket")
_N = 1 << 15
_R = 8
_P = 1
_DKLEN = 32
_SALT = 16
_NONCE = 12
_AAD = b"paws-tickets-v2"


def _passphrase_key(passphrase, salt):
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=64 * 1024 * 1024)


def _bind(appid):
    return str(uuid.uuid5(BIND_NS, f"paws://app/{appid}"))


def _encode(tickets, passphrase):
    if not tickets:
        raise ValueError("nothing to pack: no tickets")
    if not passphrase or not passphrase.strip():
        raise ValueError("passphrase can't be empty: choose one for this backup")
    for t in tickets:
        if t.key not in _RECOGNISED or not validate_payload(t.payload):
            raise ValueError(f"{t.filename} payload looks damaged - fix or delete it, then pack again")
    appids = {t.appid for t in tickets}
    if len(appids) != 1:
        raise ValueError(f"tickets from more than one app: {sorted(appids)}")
    appid = next(iter(appids))
    steam_id = next((t.steam_id for t in tickets if t.steam_id), "")
    body = {
        "v": _VERSION,
        "uid": str(uuid.uuid4()),
        "bind": _bind(appid),
        "appid": appid,
        "steamId": steam_id,
        "tickets": [{"key": t.key, "payload": t.payload} for t in tickets],
    }
    raw = _HEADER + json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    salt = os.urandom(_SALT)
    nonce = os.urandom(_NONCE)
    sealed = AESGCM(_passphrase_key(passphrase, salt)).encrypt(nonce, raw, _AAD)
    blob = salt + nonce + sealed
    return MAGIC_ENC + base64.b85encode(blob).decode()


def pack_tickets(appid: str, passphrase: str) -> str:
    mine = [t for t in list_tickets() if t.appid == appid]
    if not mine:
        raise ValueError(f"no cached tickets for appid {appid} (make one first)")
    mine.sort(key=lambda t: not t.encrypted)
    return _encode(mine, passphrase)


def _decode(data, passphrase):
    if not data:
        raise ValueError("that isn't a paws ticket string (it starts with paws1e.)")
    if data.startswith(MAGIC_LEGACY):
        raise ValueError("that's an old paws1 string with no passphrase protection - make a new backup instead")
    if not data.startswith(MAGIC_ENC):
        raise ValueError("that isn't a paws ticket string (it starts with paws1e.)")
    if not passphrase:
        raise ValueError("passphrase needed to open this backup")
    try:
        blob = base64.b85decode(data[len(MAGIC_ENC) :])
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"can't read that ticket string: {e}") from None
    if base64.b85encode(blob).decode() != data[len(MAGIC_ENC) :]:
        raise ValueError("the string got cut or changed (base85 doesn't line up)")
    if len(blob) < _SALT + _NONCE + 16:
        raise ValueError("string too short to be a backup")
    salt, nonce, sealed = blob[:_SALT], blob[_SALT : _SALT + _NONCE], blob[_SALT + _NONCE :]
    try:
        raw = AESGCM(_passphrase_key(passphrase, salt)).decrypt(nonce, sealed, _AAD)
    except InvalidTag:
        raise ValueError("wrong passphrase, or the string was altered") from None
    if not raw.startswith(_HEADER):
        raise ValueError("not a paws backup string")
    try:
        body = json.loads(raw[5:].decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"can't read that ticket string: {e}") from None

    if body.get("v") != _VERSION:
        raise ValueError(f"unknown string version {body.get('v')!r}")
    appid = str(body.get("appid") or "")
    if not appid or not appid.isdigit():
        raise ValueError("no appid in the string")
    if body.get("bind") != _bind(appid):
        raise ValueError("this string is for a different app")
    steam_id = str(body.get("steamId") or "")
    tickets = []
    for item in body.get("tickets") or []:
        key = item.get("key")
        payload = item.get("payload")
        if key not in _RECOGNISED or not validate_payload(payload):
            raise ValueError("one of the tickets in there is damaged")
        tickets.append(Ticket(appid=appid, encrypted=key == "encryptedTicket", steam_id=steam_id, payload=payload))
    if not tickets:
        raise ValueError("no tickets inside the string")
    tickets.sort(key=lambda t: not t.encrypted)
    return tickets


def unpack(data: str, passphrase: str) -> list[Ticket]:
    return _decode(data, passphrase)


def restore(data: str, passphrase: str, backup: bool = True) -> list[Ticket]:
    tickets = _decode(data, passphrase)
    from .tickets import save_ticket

    saved = []
    for t in tickets:
        saved.append(save_ticket(t.appid, t.to_yaml(), backup=backup))
    return saved


def detail_text(appid: str, width: int = 72) -> str:
    mine = [t for t in list_tickets() if t.appid == appid]
    if not mine:
        raise ValueError(f"no cached tickets for appid {appid}")
    mine.sort(key=lambda t: not t.encrypted)
    steam_id = next((t.steam_id for t in mine if t.steam_id), "")
    lines = [f"tickets for appid {appid}   steamId {steam_id}", "-" * width]
    for t in mine:
        preview = t.payload[:48] + ("…" if len(t.payload) > 48 else "")
        lines.append(f"[{t.filename}]")
        lines.append(f"  kind:    {'encrypted' if t.encrypted else 'normal'}")
        lines.append(f"  size:    {t.size} bytes")
        lines.append(f"  payload: {preview}")
        lines.append("")
    return "\n".join(lines).rstrip()


__all__ = ["pack_tickets", "unpack", "restore", "detail_text", "_decode", "_encode"]
