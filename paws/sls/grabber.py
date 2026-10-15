"""asks steam for the tickets without the game. a tiny process starts with SteamAppId=<appid>, loads steam's own
libsteam_api.so and requests an encrypted app ticket.

it then writes the result into SLSsteam's ticket cache itself, rather than waiting for SLSsteam to do it.
that's the whole trick behind not having to restart steam: SLSsteam's recvEncryptedAppTicket falls back to
reading `<config>/cache/encryptedTicket_<appid>.yaml` whenever the live request doesn't come back with one
(src/feats/ticket.cpp), and its file watcher hot-reloads that directory - so a ticket paws writes is picked
up by the steam that's already running. it also works with no SLSsteam installed at all, which is the
grabber-only path.

run as `python -m paws.sls.grabber <appid> <timeout> <lib> [cache dir]` from grab(), never imported into a
long-lived process: SteamAPI_Init ties the whole process to that one appid"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

INIT_OK = 0
SETTLE = 3.0  # keep the pipe open a moment after the ticket so the ownership ticket can land too


def api_lib() -> Path | None:
    """steam ships libsteam_api.so in its own runtime folder, so no game has to provide one"""
    from ..steam.find import find_steam

    st = find_steam()
    roots = [Path(st.root)] if st and st.root else []
    roots += [Path.home() / ".local/share/Steam", Path.home() / ".steam/steam"]
    for root in roots:
        lib = root / "steamrt64/libsteam_api.so"
        if lib.exists():
            return lib
    return None


class GrabResult:
    """what the helper managed to do. `error` set means nothing was written; `wrote_cache` says
    whether the ticket is now sitting in SLSsteam's cache for the steam that's already running"""

    def __init__(self, error: str | None = None, appid: str = "", steam_id: str = "", payload: str = "", size: int = 0):
        self.error = error
        self.appid = appid
        self.steam_id = steam_id
        self.payload = payload
        self.size = size
        self.wrote_cache = False
        self.cache_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def cache_dir_for() -> Path:
    """where SLSsteam keeps tickets: <config>/cache. falls back to the usual spot when SLSsteam
    isn't installed, so the grabber-only path still lands somewhere real"""
    from .tickets import _ensure_cache_dir

    return _ensure_cache_dir()


def grab(appid: str, timeout: float, write_cache: bool = True) -> GrabResult:
    """run the helper. returns a GrabResult - never raises for the ordinary failures"""
    lib = api_lib()
    if lib is None:
        return GrabResult("couldn't find steam's libsteam_api.so (steamrt64)")
    env = dict(os.environ, SteamAppId=str(appid), SteamGameId=str(appid))
    env.pop("LD_AUDIT", None)
    argv = [sys.executable, "-m", "paws.sls.grabber", str(appid), str(timeout), str(lib)]
    if write_cache:
        argv.append(str(cache_dir_for()))
    try:
        done = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout + 15)
    except subprocess.TimeoutExpired:
        return GrabResult("the ticket helper hung", appid=str(appid))
    if done.returncode != 0:
        lines = done.stdout.strip().splitlines() or [f"the ticket helper failed ({done.returncode})"]
        return GrabResult(lines[-1], appid=str(appid))
    payload = _last_json(done.stdout)
    if payload is None:
        return GrabResult("the ticket helper said nothing useful", appid=str(appid))
    out = GrabResult(
        appid=str(payload.get("appid", appid)),
        steam_id=str(payload.get("steamId", "")),
        payload=str(payload.get("payload", "")),
        size=int(payload.get("size", 0)),
    )
    written = payload.get("cache")
    if written:
        out.wrote_cache = True
        out.cache_path = Path(str(written))
    return out


def _last_json(text: str) -> dict | None:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def _main(appid: str, timeout: float, lib_path: str, cache_dir: str | None = None) -> int:
    lib = ctypes.CDLL(lib_path)
    lib.SteamAPI_InitFlat.argtypes = [ctypes.c_char_p]
    lib.SteamAPI_InitFlat.restype = ctypes.c_int
    lib.SteamAPI_SteamUser_v023.restype = ctypes.c_void_p
    lib.SteamAPI_ISteamUser_RequestEncryptedAppTicket.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.SteamAPI_ISteamUser_RequestEncryptedAppTicket.restype = ctypes.c_uint64
    lib.SteamAPI_ISteamUser_GetEncryptedAppTicket.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.SteamAPI_ISteamUser_GetEncryptedAppTicket.restype = ctypes.c_bool
    try:
        lib.SteamAPI_ISteamUser_GetSteamID.restype = ctypes.c_uint64
    except AttributeError:
        pass

    error = ctypes.create_string_buffer(1024)
    if lib.SteamAPI_InitFlat(error) != INIT_OK:
        why = error.value.decode(errors="replace") or "is steam running and logged in?"
        print(f"steam wouldn't let {appid} connect: {why}")
        return 2
    try:
        user = lib.SteamAPI_SteamUser_v023()
        if not user or not lib.SteamAPI_ISteamUser_RequestEncryptedAppTicket(user, None, 0):
            print("steam refused the ticket request")
            return 3
        buf, size = ctypes.create_string_buffer(4096), ctypes.c_uint32(0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            lib.SteamAPI_RunCallbacks()
            if lib.SteamAPI_ISteamUser_GetEncryptedAppTicket(user, buf, len(buf), ctypes.byref(size)) and size.value:
                end = time.time() + SETTLE
                while time.time() < end:
                    lib.SteamAPI_RunCallbacks()
                    time.sleep(0.25)
                steam_id = _steam_id(lib, user)
                payload = base64.b64encode(buf.raw[: size.value]).decode("ascii")
                result = {"appid": appid, "steamId": steam_id, "payload": payload, "size": int(size.value)}
                written = _write_cache(appid, steam_id, payload, cache_dir)
                if written:
                    result["cache"] = str(written)
                print(json.dumps(result))
                return 0
            time.sleep(0.25)
        print("steam never sent the encrypted ticket (does this account own the game?)")
        return 4
    finally:
        lib.SteamAPI_Shutdown()


def _steam_id(lib, user) -> str:
    """the 64-bit account id SLSsteam stores alongside the ticket. 0 means we couldn't read it,
    which SLSsteam tolerates (it only uses it to spoof GetSteamID for that one app)"""
    try:
        return str(int(lib.SteamAPI_ISteamUser_GetSteamID(user)))
    except (AttributeError, OSError, ValueError, TypeError):
        return "0"


def _write_cache(appid: str, steam_id: str, payload: str, cache_dir: str | None):
    """drop the ticket where SLSsteam looks for it. same shape as Ticket::saveTicketToCache:
    steamId + base64 payload under encryptedTicket, in <config>/cache/encryptedTicket_<appid>.yaml"""
    if not cache_dir:
        return None
    try:
        d = Path(cache_dir)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"encryptedTicket_{appid}.yaml"
        path.write_text(f"steamId: {steam_id}\nencryptedTicket: {payload}\n")
        return path
    except OSError:
        return None


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None))
