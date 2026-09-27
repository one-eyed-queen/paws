from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from ..sls.model import SlsInstall
from .model import SteamInstall
from .process import is_running, kill_steam


class SteamError(Exception):
    pass


def launch_env(sls: SlsInstall | None) -> dict[str, str]:
    """env with LD_AUDIT when sls brings injector libs the guard comes first for flatpak"""
    env = dict(os.environ)
    if sls and sls.lib_dir and sls.sls_so and sls.inject_so:
        inject = sls.inject_so
        main = sls.sls_so
        if sls.kind == "flatpak":
            guard = "/app/links/$LIB/libshared-library-guard.so"  # the guard has to come first
            env["LD_AUDIT"] = f"{guard}:{str(inject)}:{str(main)}"
            env["SHARED_LIBRARY_GUARD"] = "0"
        else:
            env["LD_AUDIT"] = f"{str(inject)}:{str(main)}"
    return env


def steam_command(steam: SteamInstall | None) -> list[str]:
    if steam is None:
        exe = shutil.which("steam")
        if not exe:
            raise SteamError("couldn't find steam on your PATH or in the usual folders")
        if exe.startswith("/snap/"):
            return [exe]
        return [exe]
    if steam.kind == "flatpak" and steam.binary and "flatpak" in steam.binary:
        return ["flatpak", "run", "com.valvesoftware.Steam"]
    if steam.kind == "snap":
        return ["snap", "run", "steam"]
    if steam.binary:
        return [steam.binary]
    raise SteamError("don't know which steam binary to run")


def launch(steam: SteamInstall | None, sls: SlsInstall | None, *args: str, wait: float = 0.0):
    command = steam_command(steam)
    command += list(args)
    env = launch_env(sls)
    try:
        with open(os.devnull, "w") as dn:
            subprocess.Popen(
                command,
                env=env,
                stdout=dn,
                stderr=dn,
                start_new_session=True,
            )
    except FileNotFoundError:
        raise SteamError(f"steam binary not found: {command[0]}")
    if wait:
        time.sleep(wait)


def run_game_id(appid: str | int, steam: SteamInstall | None, sls: SlsInstall | None, wait: float = 0.0):
    launch(steam, sls, f"steam://rungameid/{appid}", wait=wait)


def run_applaunch(appid: str | int, steam: SteamInstall | None, sls: SlsInstall | None, wait: float = 0.0):
    launch(steam, sls, "-applaunch", str(appid), wait=wait)


def sls_injected() -> bool:
    """is the running steam carrying the sls audit libs. LD_AUDIT only applies at
    process start, so a live steam we did not launch under injection can't get it now"""
    from .process import helper_pids, steam_pids

    for pid in steam_pids() + helper_pids():
        for leaf in ("environ", "maps"):
            try:
                blob = Path(f"/proc/{pid}/{leaf}").read_bytes().lower()
            except OSError:
                continue
            if any(m in blob for m in ("slssteam", "libsls", "library-inject")):
                return True
    return False


def probe_running(appid: str | int, steam: SteamInstall | None, sls: SlsInstall | None, timeout: float = 25.0):
    """fire the game at an already-running sls-injected steam, no restart. the thin
    client wrapper just hands the uri to the live instance and exits"""
    if not is_running():
        raise SteamError("steam is not running")
    if not sls_injected():
        raise SteamError("the running steam doesn't have SLSsteam loaded, and that only happens when steam starts")
    launch(steam, sls, f"steam://rungameid/{appid}", wait=timeout)


def one_shot_inject(steam: SteamInstall | None, sls: SlsInstall | None, *args: str, timeout: float = 25.0):
    """restart steam with LD_AUDIT and run args. a steam that was already open is left running that way, so later
    activations find it injected and need no restart; one that was closed is closed again"""
    was_running = is_running()
    if was_running:
        kill_steam()
        time.sleep(1.0)
    try:
        launch(steam, sls, *args, wait=timeout)
    except BaseException:
        kill_steam()
        raise
    if not was_running:
        kill_steam()
