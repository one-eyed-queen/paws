from __future__ import annotations

import base64
import binascii
import re
import zlib

from .tickets import Ticket, list_tickets, make_ticket_file, validate_payload

# paws.<base64url>. inside: 1 byte format (bit 0 = deflated), then varint appid, varint ticket count, then for each
# ticket 1 byte flags (bit 0 encrypted, bit 1 same steam id as the ticket before), the steam id as 8 bytes unless
# bit 1, varint length and the raw ticket bytes. tickets are stored in the cache as base64 text, so storing the bytes
# themselves is where most of the saving comes from: there's no key name or repeated id left to spend characters on
MAGIC = "paws."
CODE = re.compile(r"(?<![\w.-])" + re.escape(MAGIC) + r"[A-Za-z0-9_-]{24,}")
MAX_BYTES = 256 * 1024
FLAG_DEFLATED, FLAG_ENCRYPTED, FLAG_SAME_ID = 1, 1, 2


def _varint(number: int) -> bytes:
    out = bytearray()
    while number > 0x7F:
        out.append(number & 0x7F | 0x80)
        number >>= 7
    out.append(number)
    return bytes(out)


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def take(self, count: int) -> bytes:
        if self.at + count > len(self.data):
            raise ValueError("cut off")
        piece = self.data[self.at : self.at + count]
        self.at += count
        return piece

    def varint(self) -> int:
        number = shift = 0
        while shift < 64:
            byte = self.take(1)[0]
            number |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return number
            shift += 7
        raise ValueError("bad number")


def tickets_for(appid: str, only: str | None = None) -> list[Ticket]:
    """only: "encrypted" or "normal" to send just that one"""
    mine = sorted((t for t in list_tickets() if t.appid == str(appid)), key=lambda t: not t.encrypted)
    if only:
        mine = [t for t in mine if t.encrypted == (only == "encrypted")]
    return mine


def make_code(appid: str, only: str | None = None) -> str:
    """the shortest line that still rebuilds the exact tickets. no passphrase: anyone holding the code can use them,
    which is the point of sharing and why passphrase backups stay their own thing"""
    mine = tickets_for(appid, only)
    if not mine:
        which = f"{only} ticket" if only else "tickets"
        raise ValueError(f"no cached {which} for appid {appid} (make one first)")
    body = bytearray(_varint(int(appid)) + _varint(len(mine)))
    last_id = None
    for ticket in mine:
        raw = base64.b64decode(ticket.payload)
        if base64.b64encode(raw).decode() != ticket.payload or not ticket.steam_id.isdigit():
            raise ValueError(f"{ticket.filename} doesn't look like a real ticket, so it can't be shared")
        same = ticket.steam_id == last_id
        body.append((FLAG_ENCRYPTED if ticket.encrypted else 0) | (FLAG_SAME_ID if same else 0))
        if not same:
            body += int(ticket.steam_id).to_bytes(8, "little")
        body += _varint(len(raw)) + raw
        last_id = ticket.steam_id
    packed = zlib.compress(bytes(body), 9)
    blob = bytes([FLAG_DEFLATED]) + packed if len(packed) < len(body) else bytes([0]) + bytes(body)
    return MAGIC + base64.urlsafe_b64encode(blob).decode().rstrip("=")


def find_code(text: str) -> str | None:
    """a code still counts inside whatever message it arrived in"""
    match = CODE.search(text or "")
    return match.group(0) if match else None


def read_code(code: str) -> dict:
    """-> {"appid", "tickets": [{"steamId", "payload", "encrypted"}]}. raises ValueError on anything off"""
    data = code[len(MAGIC) :] if code.startswith(MAGIC) else ""
    try:
        blob = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        if not blob or blob[0] > FLAG_DEFLATED:
            raise ValueError("unknown format")
        body = blob[1:]
        if blob[0] == FLAG_DEFLATED:
            unpacker = zlib.decompressobj()
            body = unpacker.decompress(body, MAX_BYTES)
            if unpacker.unconsumed_tail:
                raise ValueError("too big")
        reader = _Reader(body)
        appid, count = reader.varint(), reader.varint()
        if not 1 <= count <= 8:
            raise ValueError("bad ticket count")
        rows, steam_id = [], None
        for _ in range(count):
            flags = reader.take(1)[0]
            if not flags & FLAG_SAME_ID:
                steam_id = str(int.from_bytes(reader.take(8), "little"))
            elif steam_id is None:
                raise ValueError("no steam id")
            payload = base64.b64encode(reader.take(reader.varint())).decode()
            if not validate_payload(payload):
                raise ValueError("bad ticket")
            rows.append({"steamId": steam_id, "payload": payload, "encrypted": bool(flags & FLAG_ENCRYPTED)})
    except (binascii.Error, zlib.error, ValueError) as error:
        raise ValueError("that ticket code is damaged or cut off") from error
    return {"appid": str(appid), "tickets": rows}


def describe(appid: str, rows: list[dict]) -> str:
    """what a code holds, for both ends to read"""
    lines = [f"appid  {appid}"]
    for row in rows:
        kind = "encrypted" if row["encrypted"] else "normal"
        lines.append(f"{kind:<9} steam id {row['steamId']}, {len(row['payload'])} chars")
    return "\n".join(lines)


def take_code(text: str, add_game: bool = True) -> list[Ticket]:
    """save the tickets, and add the game unless you already have it, so it's ready to play"""
    code = find_code(text)
    if code is None:
        raise ValueError(f"no ticket code there (they start with {MAGIC})")
    body = read_code(code)
    appid = body["appid"]
    saved = [make_ticket_file(appid, r["steamId"], r["payload"], r["encrypted"]) for r in body["tickets"]]
    if add_game:
        from ..games.apply import apply_plan
        from ..games.background import _plan
        from ..games.plan import _in_library

        if not _in_library(appid):
            apply_plan(_plan(appid, ""), nudge=False)
    return saved
