from __future__ import annotations

import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

from .errors import SlsError


def extract_archive(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(destination)
        return
    try:
        import py7zr

        with py7zr.SevenZipFile(archive) as z:
            z.extractall(destination)
        return
    except ImportError:
        pass
    except Exception:
        pass
    exe = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    if exe:
        r = subprocess.run([exe, "x", "-y", f"-o{destination}", str(archive)], capture_output=True)
        if r.returncode == 0:
            return
    raise SlsError(f"cannot extract {archive.name}: install python py7zr or the 7z binary")


def file_sha256(archive):
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_inner(staging):
    if (staging / "bin" / "SLSsteam.so").exists() or (staging / "SLSsteam.so").exists():
        return staging
    if staging.exists():
        tops = [p for p in staging.iterdir() if p.is_dir()]
        if len(tops) == 1:
            return tops[0]
    return staging
