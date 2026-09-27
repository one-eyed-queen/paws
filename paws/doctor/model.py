from __future__ import annotations

from dataclasses import dataclass, field

from ..config.seed import fill_missing
from ..config.where import find_config
from ..sls.find import find_sls
from ..steam.find import find_steam
from .client_check import client_check
from .config_check import config_checks
from .repair_check import repair_checks
from .result import CheckResult
from .sls_check import sls_checks
from .steam_check import steam_checks
from .term_check import term_checks
from .tools_check import tools_checks
from .upstream_check import upstream_config_check


@dataclass
class Doctor:
    checks: list[CheckResult] = field(default_factory=list)

    def run(self) -> Doctor:
        steam = find_steam()
        sls = find_sls()
        self.checks += steam_checks(steam)
        self.checks += tools_checks()
        self.checks += term_checks()
        self.checks += sls_checks(sls)
        if steam and sls:
            self.checks += client_check(steam, sls)
        self.checks += config_checks(find_config())
        self.checks += upstream_config_check(sls.lib_dir if sls else None)
        self.checks += repair_checks()
        return self

    def fix(self) -> list[str]:
        config_path = find_config()
        return fill_missing(config_path) if config_path else []

    @property
    def fail_count(self) -> int:
        return len([c for c in self.checks if c.severity == "error"])

    def report(self) -> str:
        lines = []
        for c in self.checks:
            mark = "OK " if c.severity == "ok" else ("!! " if c.severity == "error" else "-- ")
            lines.append(f"{mark}[{c.severity.upper():5}] {c.label}: {c.detail}")
        return "\n".join(lines)


def run() -> Doctor:
    return Doctor().run()
