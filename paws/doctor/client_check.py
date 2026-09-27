from __future__ import annotations

from .. import sls as sls_module
from ..config.scalars import get_scalar
from ..steam import client_hash
from .result import CheckResult

LABEL = "Steam client hash"


def _safe_mode_on():
    return (get_scalar("SafeMode") or "no").split()[0].lower() in ("yes", "true", "on", "y")


def client_check(steam, sls) -> list:
    installed = sls_module.installed_tag(sls)
    cc = client_hash.check_client(steam, sls, latest_tag=sls_module.fetch_latest_github_tag(), installed_tag=installed)
    if cc.error and not cc.sha256:
        return [CheckResult(True, LABEL, cc.error, "info")]
    short = cc.sha256[:12] + "..."
    if not cc.known_tags:
        return [CheckResult(True, LABEL, f"{short} (couldn't load updates.yaml to compare)", "info")]
    if cc.ok_for_installed:
        return [CheckResult(True, LABEL, f"{short} is on SLSsteam {installed}'s known-good list", "ok")]

    safe = _safe_mode_on()
    consequence = (
        " (SafeMode is on, so it will refuse to load)"
        if safe
        else " (only matters with SafeMode / WarnHashMissmatch on)"
    )
    if cc.ok_for_latest:
        why = f"installed {installed or '?'} has no entry for it" if installed else "installed version unknown"
        message = f"{short} is known-good for SLSsteam {cc.latest_tag} but {why}: update SLSsteam"
    else:
        message = f"{short} is on no SLSsteam release's known-good list: Steam updated past SLSsteam"
    return [CheckResult(True, LABEL, message + consequence, "warn" if safe else "info")]
