from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from ..paths import HOME, default_config_dir
from .archive import file_sha256, stage_inner, extract_archive
from .desktop import write_launcher
from .errors import SlsError
from .find import find_sls
from .model import SlsInstall
from . import private
from .release import SlsSource, download, resolve_source


def merge_user_config(release, user_config_path):
    from .. import config

    if not user_config_path.exists():
        release_config = release / "res" / "config.yaml"
        if release_config.exists():
            shutil.copy2(release_config, user_config_path)
        else:
            user_config_path.write_text(config.default_config_text())
    config.fill_missing(user_config_path)


def install_release(
    source: SlsSource,
    destination: Path | None = None,
    write_desktop: bool = True,
    merge_config: bool = True,
    progress=None,
) -> SlsInstall:
    from ..windows import IS_WINDOWS

    if IS_WINDOWS:
        from ..windows import port

        port.unsupported()
    destination = destination or HOME / ".local/share/SLSsteam"
    download_dir = HOME / ".cache/paws"
    if source.kind == "private":
        if not source.url:
            raise SlsError("a private build needs a repo link or a .zip/.7z file")
        archive, name, downloaded = private.fetch(source.url, download_dir, progress)
    elif source.kind == "local":
        archive = Path(source.url or "").expanduser()
        if not archive.is_file():
            raise SlsError(f"local file not found: {archive}")
        name, downloaded = source.name, False
    else:
        url, name = resolve_source(source)
        archive = download(url, download_dir, progress)
        downloaded = True
    staging = download_dir / f"paws-stage-{int(time.time())}"
    try:
        return _install_staged(source, name, archive, staging, destination, write_desktop, merge_config)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if downloaded:
            archive.unlink(missing_ok=True)


def _install_staged(
    source,
    name,
    archive,
    staging,
    destination,
    write_desktop,
    merge_config,
):
    extract_archive(archive, staging)
    inner = stage_inner(staging)

    bin_dir = inner / "bin"
    libs = [f for f in bin_dir.iterdir() if f.is_file()] if bin_dir.is_dir() else sorted(inner.glob("*.so"))
    if not libs:
        raise SlsError(f"{archive.name} has no built library in it (a bin/ folder or .so files): source code won't do")
    destination.mkdir(parents=True, exist_ok=True)
    for lib in libs:
        shutil.copy2(lib, destination / lib.name)
    tools_source = inner / "tools"
    if tools_source.exists():
        tools_destination = destination / "tools"
        shutil.rmtree(tools_destination, ignore_errors=True)
        shutil.copytree(tools_source, tools_destination)
    res_source = inner / "res"
    if res_source.exists():
        res_destination = destination / "res"
        shutil.rmtree(res_destination, ignore_errors=True)
        shutil.copytree(res_source, res_destination)
    docs_source = inner / "docs" / "LICENSE"
    if docs_source.exists():
        shutil.copytree(docs_source, destination / "docs" / "LICENSE", dirs_exist_ok=True)
    if merge_config:
        config_dir = default_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        merge_user_config(inner, config_dir / "config.yaml")
    info = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": source.kind,
        "source_desc": source.describe(),
        "tag": name if source.kind in ("github", "forgejo", "private") else None,
        "sha256": file_sha256(archive),
        "files": [f.name for f in destination.iterdir() if f.is_file()],
    }
    (destination / "paws.info.json").write_text(json.dumps(info, indent=2))

    if write_desktop:
        write_launcher(destination)

    return find_sls()
