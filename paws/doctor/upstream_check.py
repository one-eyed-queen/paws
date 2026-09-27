from __future__ import annotations

from pathlib import Path

from ..config import upstream
from .result import CheckResult


def _drift_result(label, id_suffix, added, removed):
    if not added and not removed:
        return CheckResult(True, "Config schema", f"matches {label}", "ok")
    bits = []
    if added:
        bits.append(f"new: {', '.join(added)}")
    if removed:
        bits.append(f"gone: {', '.join(removed)}")
    return CheckResult(True, f"Config schema vs {label}", "; ".join(bits), "warn")


def upstream_config_check(lib_dir: Path | None = None) -> list:
    out = []
    github_keys = upstream.fetch_github_keys()
    if github_keys is None:
        out.append(CheckResult(True, "Config schema", "couldn't check against github (offline, or it's down)", "info"))
    else:
        out.append(_drift_result("SLSsteam's latest on github", "github", *upstream.diff(github_keys)))
    installed_keys = upstream.installed_template_keys(lib_dir)
    if installed_keys is not None:
        result = _drift_result(
            "the template your installed SLSsteam shipped with", "installed", *upstream.diff(installed_keys)
        )
        if result.severity != "ok":
            out.append(result)
    return out
