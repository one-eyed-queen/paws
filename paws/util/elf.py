"""just enough ELF for two questions about a library: is it 32 or 64 bit, and does a byte pattern sit in its code"""

from __future__ import annotations

import re
import struct
from pathlib import Path


def bits(path) -> int | None:
    """32 or 64 from the ELF header, None for anything that isn't an ELF file"""
    try:
        with open(path, "rb") as f:
            head = f.read(5)
    except OSError:
        return None
    if len(head) < 5 or head[:4] != b"\x7fELF":
        return None
    return {1: 32, 2: 64}.get(head[4])


def code(path) -> bytes:
    """the .text section, where SLSsteam's memhlp.patternScan looks. b"" when there isn't one"""
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF" or data[4] not in (1, 2):
        return b""
    end = "<" if data[5] == 1 else ">"
    if data[4] == 1:
        (shoff,) = struct.unpack_from(end + "I", data, 0x20)
        entsize, count, names = struct.unpack_from(end + "HHH", data, 0x2E)
        layout = end + "IIIIII"
    else:
        (shoff,) = struct.unpack_from(end + "Q", data, 0x28)
        entsize, count, names = struct.unpack_from(end + "HHH", data, 0x3A)
        layout = end + "IIQQQQ"

    def section(i):
        name, _kind, _flags, _addr, offset, size = struct.unpack_from(layout, data, shoff + i * entsize)
        return name, offset, size

    try:
        _name, table, _size = section(names)
        for i in range(count):
            name, offset, size = section(i)
            if data[table + name : data.index(b"\0", table + name)] == b".text":
                return data[offset : offset + size]
    except (struct.error, ValueError):
        pass
    return b""


def matches(pattern: str, data: bytes) -> int:
    """how often an IDA-style pattern like "E8 ? ? ? ? 83 C4" occurs in data"""
    parts = [b"." if token.strip("?") == "" else re.escape(bytes([int(token, 16)])) for token in pattern.split()]
    return len(re.findall(b"".join(parts), data, re.DOTALL))
