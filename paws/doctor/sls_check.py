from __future__ import annotations

from .. import sls as sls_module
from ..util import pkgmgr
from .result import CheckResult


def sls_checks(sls) -> list:
    headcrab = sls_module.headcrab.footprint()
    if not sls and not headcrab:
        return [
            CheckResult(False, "No SLSsteam or HeadCrab found", "install one from Install / Update SLSsteam", "error"),
            CheckResult(False, "SLSsteam NOT installed", "use Install/Update SLSsteam", "warn"),
        ]
    if not sls:
        return [
            CheckResult(True, "HeadCrab found", f"{len(headcrab)} thing(s) of it on this machine", "info"),
            CheckResult(False, "SLSsteam NOT installed", "use Install/Update SLSsteam", "warn"),
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
