from __future__ import annotations

import os

from .. import sls as sls_module
from ..util import pkgmgr
from .result import CheckResult


def sls_checks(sls) -> list:
    if os.name == "nt":
        from ..windows import port
        from ..windows.port import BLOCKED_WITHOUT_PORT, WORKS_WITHOUT_PORT

        seen = port.status()
        out = []
        if seen["port"] == "openvalve":
            out.append(
                CheckResult(
                    True,
                    "OpenValve detected",
                    f"managing {seen['openvalve_config']} - it's a manager, so there is nothing to install "
                    "or update; paws reads and writes that config directly",
                    "ok",
                )
            )
        elif seen["port"] == "hubcaptools":
            out.append(
                CheckResult(
                    True,
                    "HubCapTools detected",
                    f"proxy dll at {seen['dll']} (installed={seen['version'] or 'unknown'})",
                    "ok",
                )
            )
        elif seen["has_config"]:
            out.append(
                CheckResult(
                    False,
                    "HubCapTools config but no proxy dll",
                    f"config at {seen['config_dir']} but {port.DLL_NAME} isn't next to steam.exe, so it won't load",
                    "warn",
                )
            )
        else:
            out.append(
                CheckResult(
                    False,
                    "HubCapTools not installed",
                    "use Install / Update SLSsteam - it fetches the installer from "
                    f"{port.HUB_CAP_REPO} and verifies it. steam has to be closed first",
                    "warn",
                )
            )
        out.append(CheckResult(True, "What works on windows anyway", WORKS_WITHOUT_PORT, "info"))
        out.append(
            CheckResult(
                True,
                "Still blocked",
                f"ticket generation (needs a port that can serve them): {BLOCKED_WITHOUT_PORT}",
                "info",
            )
        )
        return out
    headcrab = sls_module.headcrab.footprint()
    if not sls and not headcrab:
        return [
            CheckResult(False, "No SLSsteam or HeadCrab found", "install one from Install / Update SLSsteam", "error"),
            CheckResult(False, "SLSsteam NOT installed", "use Install/Update SLSsteam", "warn"),
        ]
    if not sls:
        return [
            CheckResult(True, "HeadCrab found", f"{len(headcrab)} thing(s) of it on this machine", "info"),
            # headcrab is its own SLSsteam build rather than a wrapper, so there's nothing to fix -
            # it just brings its own copy. say that instead of telling them to install it again
            CheckResult(
                True,
                "SLSsteam not installed separately",
                "HeadCrab installs SLSsteam underneath itself, so this is expected - nothing to do",
                "ok",
            ),
        ]
    out = [
        CheckResult(
            True,
            "SLSsteam detected",
            f"{sls.kind} so={sls.sls_so} cfg={sls.config} desktop_ldaudit={sls.desktop_used}",
            "ok",
        )
    ]
    if headcrab:
        out.append(CheckResult(True, "HeadCrab found", f"{len(headcrab)} thing(s) of it on this machine", "info"))
    if sls.desktop_used:
        out.append(CheckResult(True, "LD_AUDIT wired", "a launcher (.desktop) injects SLSsteam", "ok"))
    version = sls_module.installed_version(sls)
    latest = sls_module.fetch_latest_github_tag()
    if not version:
        out.append(CheckResult(True, "SLS version", f"latest={latest}", "info"))
    elif sls_module.update_available(sls, latest):
        how = f" (update it with: {pkgmgr.update_hint('slssteam', sls.managed_by)})" if sls.managed_by else ""
        out.append(CheckResult(True, "Update available", f"installed={version} latest={latest}{how}", "warn"))
    else:
        out.append(CheckResult(True, "SLS version", f"installed={version} latest={latest}", "ok"))
    return out
