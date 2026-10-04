from __future__ import annotations

import re
from pathlib import Path

from .find import find_steam


def config_vdf() -> Path | None:
    st = find_steam()
    if st and st.config_vdf:
        return Path(st.config_vdf)
    for cand in (
        Path.home() / ".steam/root/config/config.vdf",
        Path.home() / ".steam/steam/config/config.vdf",
    ):
        if cand.exists():
            return cand
    return None


def read_vdf(path: Path | None = None) -> str:
    p = path or config_vdf()
    if not p or not p.exists():
        return ""
    return p.read_text(errors="replace")


def _detect_indent(text, position):
    line_start = text.rfind("\n", 0, position)
    if line_start == -1:
        return ""
    prefix = text[line_start + 1 : position]
    m = re.match(r"(\t+)", prefix)
    return m.group(0) if m else "\t"


def _make_depot_block(depot_id, key_hash, vdf):
    existing = re.search(r'\t+"(\d+)"\s*\{', vdf)
    indent = existing.group(0).split('"')[0] if existing else "\t" * 5
    return f'{indent}"{depot_id}"\n{indent}{{\n{indent}\t"DecryptionKey"\t\t"{key_hash}"\n{indent}}}'


def _merge_depot_keys(content: str, depots: dict[str, str]) -> tuple[str, int]:
    injected = 0
    for depot_id, key_hash in depots.items():
        depot_pattern = rf'"{re.escape(depot_id)}"\s*\{{'
        dm = re.search(depot_pattern, content)
        if dm:
            block_start = dm.start()
            depth = 0
            block_end = block_start
            for i in range(dm.end(), len(content)):  # count the braces to walk out of the block
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    if depth == 0:
                        block_end = i + 1
                        break
                    depth -= 1
            block = content[block_start:block_end]
            if '"DecryptionKey"' in block:
                continue
            insert_at = dm.end()
            indent = _detect_indent(content, insert_at) + "\t"
            line = f'\n{indent}"DecryptionKey"\t\t"{key_hash}"'
            content = content[:insert_at] + line + content[insert_at:]
            injected += 1
        else:
            section = re.search(r'"depots"\s*\n\s*\{', content)
            block = _make_depot_block(depot_id, key_hash, content)
            if section:
                insert_at = section.end()
                content = content[:insert_at] + "\n" + block + content[insert_at:]
            else:
                content = content.rstrip() + '\n\n\t"depots"\n\t{\n' + block + "\n\t}\n"
            injected += 1
    return content, injected


def _count_verified(content: str, depots: dict[str, str]) -> int:
    verified = 0
    for did in depots:
        i = content.find(f'"{did}"')
        if i != -1 and "DecryptionKey" in content[i : i + 250]:
            verified += 1
    return verified


def inject_depot_keys(depots: dict[str, str], backup: bool = True, path: Path | None = None, retries: int = 3) -> dict:
    from ..util.backup import backup_file

    p = path or config_vdf()
    if p is None:
        return {"error": "no config.vdf, steam not found"}
    bak = backup_file(p) if backup else None
    content = read_vdf(p)
    if not content:
        return {"error": "config.vdf is empty"}

    new_content, injected = _merge_depot_keys(content, depots)
    _write(p, new_content)

    # steam itself can rewrite config.vdf while it's running (e.g. on exit), which can race
    # our own write and silently lose it - re-read, re-merge and rewrite a few times rather
    # than trusting a single write actually stuck
    verified = _count_verified(read_vdf(p), depots)
    for _attempt in range(retries - 1):
        if verified:
            break
        content = read_vdf(p)
        new_content, injected = _merge_depot_keys(content, depots)
        if not injected:
            break
        _write(p, new_content)
        verified = _count_verified(read_vdf(p), depots)

    return {"injected": injected, "verified": verified, "backup": bak, "path": str(p)}


def _write(p, content):
    import os

    temporary_path = p.with_suffix(".paws_tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary_path, p)


def existing_depot_ids(depot_ids: list[str], path: Path | None = None) -> set[str]:
    """depots that already had a block those weren't added by us"""
    p = path or config_vdf()
    content = read_vdf(p) if p else ""
    return {d for d in depot_ids if re.search(rf'"{re.escape(d)}"\s*\{{', content or "")}


def remove_depot_keys(depot_ids: list[str], backup: bool = True, path: Path | None = None) -> dict:
    from ..util.backup import backup_file

    p = path or config_vdf()
    if p is None:
        return {"error": "no config.vdf"}
    bak = backup_file(p) if backup else None
    content = read_vdf(p)
    removed = []
    for did in depot_ids:
        dm = re.search(rf'\t*"{re.escape(did)}"\s*\{{.*?\n\t*\}}', content, re.DOTALL)
        if dm:
            content = content[: dm.start()] + content[dm.end() :]
            removed.append(did)
    if removed:
        _write(p, content)
    return {"removed": removed, "backup": bak}
