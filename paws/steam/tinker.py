"""the steam client itself: 32 or 64 bit, stable or a beta, held on its version, or rolled back to an older one.

everything here is steam's own switches, nothing patched:
  - 64 bit: steam.sh starts steamrt64/steam instead of ubuntu12_32/steam when .steam-enable-steamrt64-client exists
  - channel: package/beta holds the beta's name (steam backs out by itself when the branch 404s)
  - hold: BootStrapperInhibitAll=enable in steam.cfg stops the updater
  - rollback: the old manifest comes from the web archive, the files from valve's own cdn (it keeps old ones), and
    steam's updater installs them through -overridepackageurl pointed at a tiny relay on 127.0.0.1"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..util import backup, elf, http
from .model import SteamInstall

ARCH_MARKER = ".steam-enable-steamrt64-client"
HOLD_KEY = "BootStrapperInhibitAll"
CDN = "https://client-update.fastly.steamstatic.com"
ARCHIVE_HOSTS = (
    "media.steampowered.com/client",
    "client-update.fastly.steamstatic.com",
    "client-update.akamai.steamstatic.com",
)
# (branch, label, what it is). "" is the normal release
BRANCHES = (
    ("", "stable", "the normal release everybody gets"),
    ("publicbeta", "beta", "steam's public beta: new stuff first, SLSsteam may not support it yet"),
    ("steamdeck_stable", "steam deck stable", "the deck's release channel"),
    ("steamdeck_publicbeta", "steam deck beta", "the deck's beta channel"),
)
_BRANCH_RE = re.compile(r"[a-z0-9_]{1,64}")


class TinkerError(Exception):
    pass


@dataclass
class ClientState:
    root: Path | None = None
    kind: str = ""
    version: str | None = None
    channel: str = ""
    bits: int | None = None
    can_64: bool = False
    held: bool = False
    sls_bits: int | None = None
    running: bool = False
    forced: str = ""

    @property
    def channel_label(self) -> str:
        return next((label for name, label, _ in BRANCHES if name == self.channel), self.channel or "stable")

    @property
    def sls_fits(self) -> bool | None:
        if not self.sls_bits or not self.bits:
            return None
        return self.sls_bits == self.bits


@dataclass(frozen=True)
class Build:
    stamp: str
    host: str

    @property
    def date(self) -> str:
        s = self.stamp
        return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"

    def url(self, platform: str = "ubuntu12") -> str:
        return f"https://web.archive.org/web/{self.stamp}id_/http://{self.host}/steam_client_{platform}"


def _find(steam: SteamInstall | None) -> SteamInstall:
    if steam is None:
        from .find import find_steam

        steam = find_steam()
    if steam is None or steam.root is None:
        raise TinkerError("couldn't find a steam install")
    if steam.kind == "windows":
        raise TinkerError("the steam client switches here are linux only")
    return steam


def package_dir(root: Path) -> Path:
    return root / "package" if (root / "package").exists() else root.parent / "package"


def can_64(root: Path) -> bool:
    exe = root / "steamrt64" / "steam"
    return os.access(exe, os.X_OK) and elf.bits(root / "steamrt64" / "steamclient.so") == 64


def forced_client() -> str:
    """STEAM_FORCE_CLIENT in paws' own environment. steam.sh turns it into the marker file on the next start"""
    return os.environ.get("STEAM_FORCE_CLIENT", "").strip()


def active_bits(root: Path) -> int:
    forced = forced_client()
    if forced in ("ubuntu12_32", "scout", "ldlp"):
        return 32
    wants_64 = forced in ("steamrt64", "steamrt3c", "steamrt") or (root / ARCH_MARKER).exists()
    return 64 if wants_64 and can_64(root) else 32


def client_dir(root: Path) -> str:
    return "steamrt64" if active_bits(root) == 64 else "ubuntu12_32"


def active_client(root: Path) -> Path | None:
    """the steamclient.so the steam client that starts here loads, the one SLSsteam has to hook"""
    path = root / client_dir(root) / "steamclient.so"
    return path if path.is_file() else None


def channel(root: Path) -> str:
    try:
        return (package_dir(root) / "beta").read_text().strip()
    except OSError:
        return ""


def _cfg(root: Path) -> Path:
    for name in ("steam.cfg", "Steam.cfg"):
        if (root / name).exists():
            return root / name
    return root / "steam.cfg"


def held(root: Path) -> bool:
    try:
        text = _cfg(root).read_text()
    except OSError:
        return False
    return any(
        _cfg_key(line) == HOLD_KEY.lower() and line.split("=", 1)[1].strip().lower() == "enable"
        for line in text.splitlines()
        if "=" in line
    )


def _cfg_key(line: str) -> str:
    return line.split("=", 1)[0].strip().lower()


def state(steam: SteamInstall | None = None) -> ClientState:
    steam = _find(steam)
    root = Path(steam.root)
    from ..sls.find import find_sls
    from .find import _client_version
    from .process import is_running

    try:
        sls = find_sls()
    except (ImportError, OSError):
        sls = None
    return ClientState(
        root=root,
        kind=steam.kind,
        version=_client_version(steam)[0],
        channel=channel(root),
        bits=active_bits(root),
        can_64=can_64(root),
        held=held(root),
        sls_bits=elf.bits(sls.sls_so) if sls and sls.sls_so else None,
        running=is_running(),
        forced=forced_client(),
    )


def _closed():
    from .process import is_running

    if is_running():
        raise TinkerError("close steam first (from its own menu), it only reads these when it starts")


def set_bits(steam: SteamInstall | None, bits: int) -> str:
    steam = _find(steam)
    root = Path(steam.root)
    if bits not in (32, 64):
        raise TinkerError("it's 32 or 64")
    _closed()
    marker = root / ARCH_MARKER
    if bits == 64:
        if not can_64(root):
            raise TinkerError("this steam has no 64-bit client yet (steamrt64/steam is missing): update steam first")
        marker.touch()
    else:
        marker.unlink(missing_ok=True)
    note = ""
    forced = forced_client()
    if forced and active_bits(root) != bits:
        note = f". STEAM_FORCE_CLIENT={forced} is set in your environment and wins over this, unset it"
    return f"steam starts the {bits}-bit client from now on{note}"


def branch_exists(branch: str, platform: str = "ubuntu12", timeout: float = 15) -> bool:
    url = f"{CDN}/steam_client_{branch}_{platform}"
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "paws"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.status == 200
    except (urllib.error.URLError, OSError):
        return False


def set_channel(steam: SteamInstall | None, branch: str, *, check: bool = True) -> str:
    steam = _find(steam)
    root = Path(steam.root)
    branch = (branch or "").strip().lower()
    if branch in ("stable", "public", "none"):
        branch = ""
    if branch and not _BRANCH_RE.fullmatch(branch):
        raise TinkerError(f"{branch!r} isn't a branch name (lowercase letters, digits and _)")
    _closed()
    beta = package_dir(root) / "beta"
    if branch and check and not branch_exists(branch, "steamrt64" if active_bits(root) == 64 else "ubuntu12"):
        raise TinkerError(f"valve has no client branch called {branch!r} (or the cdn didn't answer)")
    backup.backup_file(beta)
    if branch:
        beta.parent.mkdir(parents=True, exist_ok=True)
        beta.write_text(branch + "\n")
        return f"steam switches to {branch} the next time it starts and updates itself onto it"
    beta.unlink(missing_ok=True)
    return "steam goes back to stable the next time it starts"


def set_hold(steam: SteamInstall | None, on: bool) -> str:
    steam = _find(steam)
    path = _cfg(Path(steam.root))
    try:
        lines = path.read_text().splitlines()
    except OSError:
        lines = []
    backup.backup_file(path)
    kept = [line for line in lines if _cfg_key(line) != HOLD_KEY.lower()]
    if on:
        kept.append(f"{HOLD_KEY}=enable")
    if kept:
        path.write_text("\n".join(kept) + "\n")
    else:
        path.unlink(missing_ok=True)
    if on:
        return "updates held: steam stays on this version until you let it update again"
    return "updates allowed again: steam updates itself the next time it starts"


def archived_builds(platform: str = "ubuntu12", timeout: float = 30, keep: int = 40) -> list[Build]:
    """older client releases the web archive saved a manifest of, newest first, one per day"""
    seen: dict[str, Build] = {}
    for host in ARCHIVE_HOSTS:
        url = (
            "https://web.archive.org/cdx/search/cdx?output=json&fl=timestamp&filter=statuscode:200"
            f"&url={host}/steam_client_{platform}"
        )
        try:
            rows = http.get_json(url, timeout=timeout)
        except (OSError, ValueError):
            continue
        for row in rows[1:]:
            stamp = str(row[0])
            if re.fullmatch(r"\d{14}", stamp):
                seen.setdefault(stamp[:8], Build(stamp, host))
    return sorted(seen.values(), key=lambda b: b.stamp, reverse=True)[:keep]


def manifest_version(text: str) -> str | None:
    m = re.search(r'"version"\s+"(\d+)"', text)
    return m.group(1) if m else None


def fetch_manifest(build: Build, platform: str = "ubuntu12", timeout: float = 60) -> tuple[bytes, str]:
    raw = http.get(build.url(platform), timeout=timeout)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    version = manifest_version(raw.decode(errors="replace"))
    if not version or f'"{platform}"' not in raw[:64].decode(errors="replace"):
        raise TinkerError(f"the archived copy from {build.date} isn't a {platform} client manifest")
    return raw, version


class _Relay(ThreadingHTTPServer):
    """the old manifest for the one platform being rolled back, everything else straight from valve"""

    daemon_threads = True

    def __init__(self, manifests: dict[str, bytes], upstream: str = CDN):
        self.manifests = manifests
        self.upstream = upstream.rstrip("/")
        self.served: list[str] = []
        super().__init__(("127.0.0.1", 0), _RelayHandler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _RelayHandler(BaseHTTPRequestHandler):
    server: _Relay

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self._answer(body=False)

    def do_GET(self):
        self._answer(body=True)

    def _answer(self, body: bool):
        name = self.path.split("?", 1)[0].lstrip("/").split("/")[-1]
        self.server.served.append(name)
        if name in self.server.manifests:
            data = self.server.manifests[name]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if body:
                self.wfile.write(data)
            return
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", name or ""):
            self.send_error(404)
            return
        url = f"{self.server.upstream}/{name}"
        request = urllib.request.Request(url, method="GET" if body else "HEAD", headers={"User-Agent": "paws"})
        try:
            with urllib.request.urlopen(request, timeout=120) as reply:
                self.send_response(reply.status)
                for header in ("Content-Type", "Content-Length"):
                    if reply.headers.get(header):
                        self.send_header(header, reply.headers[header])
                self.end_headers()
                if body:
                    shutil.copyfileobj(reply, self.wfile, 1 << 20)
        except urllib.error.HTTPError as error:
            self.send_error(error.code)
        except (urllib.error.URLError, OSError):
            try:
                self.send_error(502)
            except OSError:
                pass


def rollback(steam: SteamInstall | None, build: Build, progress=None, timeout: float = 1800) -> dict:
    """put the 32-bit client back on an archived release and hold it there. starts steam's updater, which exits
    when it's done (-exitsteam)"""
    steam = _find(steam)
    root = Path(steam.root)
    if steam.kind != "native":
        raise TinkerError(f"rollback only works on the normal (non-{steam.kind}) steam install")
    if active_bits(root) != 32:
        raise TinkerError("only 32-bit client releases are archived: switch to 32-bit first, then roll back")
    if channel(root):
        raise TinkerError("you're on a beta: switch to stable first, archived releases are stable ones")
    _closed()
    say = progress or (lambda *a, **k: None)
    say(0.05, "fetching the old manifest")
    data, target = fetch_manifest(build)
    from .find import _client_version
    from .launch import steam_command

    before = _client_version(steam)[0]
    set_hold(steam, False)
    relay = _Relay({"steam_client_ubuntu12": data})
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    env = {k: v for k, v in os.environ.items() if k not in ("LD_AUDIT", "LD_PRELOAD", "STEAM_FORCE_CLIENT")}
    command = steam_command(steam) + [
        "-forcesteamupdate",
        "-forcepackagedownload",
        "-overridepackageurl",
        relay.url,
        "-exitsteam",
    ]
    say(0.15, f"steam is installing {target} (it closes itself when done)")
    started = time.time()
    try:
        with open(os.devnull, "w") as dn:
            subprocess.run(command, env=env, stdout=dn, stderr=dn, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise TinkerError(f"steam's updater was still going after {int(timeout // 60)} min, check it and try again")
    except FileNotFoundError:
        raise TinkerError(f"steam binary not found: {command[0]}")
    finally:
        relay.shutdown()
        relay.server_close()
    after = _client_version(steam)[0]
    ok = after == target
    if ok:
        set_hold(steam, True)
    say(1.0, "done")
    return {
        "before": before,
        "after": after,
        "target": target,
        "ok": ok,
        "held": ok,
        "seconds": int(time.time() - started),
        "asked_for_manifest": "steam_client_ubuntu12" in relay.served,
    }


def describe(s: ClientState) -> dict:
    return {
        "root": str(s.root) if s.root else None,
        "version": s.version,
        "channel": s.channel or "stable",
        "bits": s.bits,
        "can_64": s.can_64,
        "held": s.held,
        "sls_bits": s.sls_bits,
        "sls_fits": s.sls_fits,
        "running": s.running,
        "forced": s.forced,
    }
