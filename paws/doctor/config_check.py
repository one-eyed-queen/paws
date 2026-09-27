from __future__ import annotations

from ..config.io import raw_lines
from ..config.scalars import get_scalar
from ..config.schema import SECTIONS
from ..config.seed import missing_keys
from ..util import backup
from .result import CheckResult


def config_keys_check(config_path) -> list:
    out = []
    missing = missing_keys(config_path)
    if missing:
        head = ", ".join(missing[:4]) + ("..." if len(missing) > 4 else "")
        out.append(
            CheckResult(
                True,
                "Config keys missing",
                f"{len(missing)} missing ({head}): SLSsteam warns on every reload. run `paws doctor --fix`",
                "warn",
            )
        )
    present = {line.split(":", 1)[0] for line in raw_lines(config_path) if line[:1].isalpha() and ":" in line}
    ignored = [k for k in SECTIONS.get("removed", []) if k in present]
    if ignored:
        out.append(
            CheckResult(
                True, "Config keys ignored", f"SLSsteam doesn't read: {', '.join(ignored)} (safe to delete)", "warn"
            )
        )
    return out


def _known_good_check(config_path):
    good = backup.known_good(config_path.name)
    if good is None:
        return CheckResult(
            True, "Known-good snapshot", "none yet, doctor saves one when the config looks clean", "info"
        )
    return CheckResult(True, "Known-good snapshot", f"{backup.age(good)}, ready to restore if this ever breaks", "info")


def config_checks(config_path) -> list:
    if not config_path:
        return [CheckResult(False, "Config missing", "no config.yaml yet", "warn")]
    return [
        CheckResult(True, "Config", str(config_path), "info"),
        CheckResult(True, "API pipe", f"API={get_scalar('API') or 'no'}", "info"),
        CheckResult(True, "Plugins (Lua)", f"Plugins={get_scalar('Plugins') or 'no'}", "info"),
        _known_good_check(config_path),
        *config_keys_check(config_path),
    ]
