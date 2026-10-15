from __future__ import annotations

import hashlib
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from .errors import SlsError

ZIP_SUFFIXES = (".zip",)
SEVENZIP_SUFFIXES = (".7z",)
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar.zst", ".tzst")
ARCHIVE_SUFFIXES = ZIP_SUFFIXES + SEVENZIP_SUFFIXES + TAR_SUFFIXES
EXTRA_SUFFIXES = (".zst", ".7zip")
# Path.suffix only ever gives the last piece, so "foo.pkg.tar.zst" reads as ".zst" - anything
# that has to recognise a tarball has to look at the whole name instead
TAR_NAMES = (".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar.zst", ".tzst")


def is_tar_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(sfx) for sfx in TAR_NAMES)


def is_archive(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.endswith(ARCHIVE_SUFFIXES + EXTRA_SUFFIXES)


def _extract_tar(archive: Path, destination: Path) -> bool:
    """plain tarballs are stdlib; the zstd ones need zstandard (or a zstd binary, or 7z)"""
    mode = "r:*"
    opener = None
    if archive.name.lower().endswith((".zst", ".tzst")):
        try:
            import zstandard
        except ImportError:
            zstd = shutil.which("zstd") or shutil.which("zstdmt")
            if not zstd:
                return False
            proc = subprocess.Popen([zstd, "-dc", str(archive)], stdout=subprocess.PIPE)
            opener = proc.stdout
            mode = "r|"
        else:
            fobj = archive.open("rb")
            dctx = zstandard.ZstdDecompressor()
            opener = dctx.stream_reader(fobj)
            mode = "r|"
    try:
        with tarfile.open(fileobj=opener, mode=mode) if opener else tarfile.open(archive, mode=mode) as t:
            _safe_extract(t, destination)
    finally:
        if opener is not None and hasattr(opener, "close"):
            try:
                opener.close()
            except Exception:
                pass
    return True


def _safe_extract(tar: tarfile.TarFile, destination: Path):
    # a tarball is just a pile of paths - refuse anything trying to escape the destination.
    # one forward pass, not getmembers() then extractall(): a stream-mode tar (which is what
    # zstd/gzip give us) can only be read forwards, so a second pass would fail on it
    root = destination.resolve()
    for member in tar:
        target = (root / member.name).resolve()
        if root != target and root not in target.parents:
            raise SlsError(f"{member.name} points outside the folder it's unpacking into")
        if member.issym() or member.islnk():
            raise SlsError(f"{member.name} is a link, not a file")
        tar.extract(member, destination)


def extract_archive(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    lowered = archive.name.lower()
    if lowered.endswith(ZIP_SUFFIXES):
        with zipfile.ZipFile(archive) as z:
            z.extractall(destination)
        return
    if is_tar_name(lowered):
        if _extract_tar(archive, destination):
            return
        exe = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
        if exe:
            r = subprocess.run([exe, "x", "-y", f"-o{destination}", str(archive)], capture_output=True)
            if r.returncode == 0:
                return
        raise SlsError(f"cannot extract {archive.name}: install python zstandard or the zstd binary")
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
