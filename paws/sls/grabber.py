"""asks steam for the tickets without the game. a tiny process starts with SteamAppId=<appid>, loads steam's own
libsteam_api.so and requests an encrypted app ticket. SLSsteam saves whatever ticket comes back into its cache
(ticket.cpp recvEncryptedAppTicket), so nothing has to be installed and steam never shows its install window.
run as `python -m paws.sls.grabber <appid> <timeout>` from grab(), never imported into a long-lived process:
SteamAPI_Init ties the whole process to that one appid"""

from __future__ import annotations

import ctypes
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


def grab(appid: str, timeout: float) -> str | None:
    """run the helper; returns an error, or None when steam answered (the tickets then show up in the cache)"""
    lib = api_lib()
    if lib is None:
        return "couldn't find steam's libsteam_api.so (steamrt64)"
    env = dict(os.environ, SteamAppId=str(appid), SteamGameId=str(appid))
    env.pop("LD_AUDIT", None)
    try:
        done = subprocess.run(
            [sys.executable, "-m", "paws.sls.grabber", str(appid), str(timeout), str(lib)],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return "the ticket helper hung"
    if done.returncode == 0:
        return None
    return (done.stdout.strip().splitlines() or [f"the ticket helper failed ({done.returncode})"])[-1]


def _main(appid: str, timeout: float, lib_path: str) -> int:
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
                return 0
            time.sleep(0.25)
        print("steam never sent the encrypted ticket (does this account own the game?)")
        return 4
    finally:
        lib.SteamAPI_Shutdown()


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1], float(sys.argv[2]), sys.argv[3]))
