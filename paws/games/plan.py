from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..manifest.bundle import ManifestBundle


@dataclass
class Change:
    target: str
    action: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.target}:{self.action}:{' '.join(self.detail.split())}"


@dataclass
class GamePlan:
    appid: str
    name: str = ""
    additional_apps: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    decryption_keys: dict[str, str] = field(default_factory=dict)
    manifest_ids: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    dlc_data: dict[str, str] = field(default_factory=dict)
    manifest_files: list[tuple[int, int, Path]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)

    def changes(self) -> list[Change]:
        out = []
        for a in self.additional_apps:
            out.append(Change("config.yaml", "add", f"AdditionalApps     {a}"))
        for d in self.decryption_keys:
            out.append(Change("config.vdf", "add", f"DecryptionKey      {d}"))
        for d, m in self.manifest_ids.items():
            out.append(Change("config.yaml", "add", f"ManifestIds        {d}:{m}"))
        for a, t in self.tokens.items():
            out.append(Change("config.yaml", "add", f"AppTokens          {a}:{t}"))
        for d, n in self.dlc_data.items():
            out.append(Change("config.yaml", "add", f"DlcData            {d}" + (f" ({n})" if n else "")))
        for d, mid, _p in self.manifest_files:
            out.append(Change("depotcache", "copymanifest", f"manifest_{d}_{mid}"))
        return out

    def counts(self) -> dict[str, int]:
        from collections import Counter

        return dict(Counter(c.target for c in self.changes()))


def plan_from_bundle(bundle: ManifestBundle, name: str = "") -> GamePlan:
    flat = bundle.flatten()
    appid = str(bundle.appid or (flat["app_ids"][0] if flat["app_ids"] else ""))
    plan = GamePlan(appid=appid, name=name or "")
    plan.additional_apps = [str(a) for a in flat["app_ids"]] or ([appid] if appid else [])
    plan.decryption_keys = {str(k): v for k, v in flat["depots"].items()}
    plan.manifest_files = flat["manifests"]
    for lm in bundle.luas:
        plan.manifest_ids.update({str(d): str(m) for d, m, _ in lm.manifest_ids})
        plan.tokens.update({str(a): str(s) for a, s, _ in lm.app_tokens})
        plan.dlc_data.update({str(d): n for d, n in lm.dlc_names.items()})
    return plan


def plan_from_info(info) -> GamePlan:
    plan = GamePlan(appid=str(info.appid), name=info.name or str(info.appid))
    plan.additional_apps = [str(info.appid)] + [str(d) for d in info.dlc_names] + [str(x) for x in info.linked]
    plan.packages = [str(p) for p in info.packages]
    plan.dlc_data = {str(d): n for d, n in info.dlc_names.items()}
    return plan


def plan_add(
    appid: str,
    name: str = "",
    packages: list[str] | None = None,
    depot_keys: dict[str, str] | None = None,
    manifest_ids: dict[str, str] | None = None,
    tokens: dict[str, str] | None = None,
    manifest_files: list[tuple[int, int, Path]] | None = None,
    dlc_data: dict[str, str] | None = None,
) -> GamePlan:
    plan = GamePlan(appid=str(appid), name=name)
    plan.additional_apps = [str(appid)]
    plan.packages = [str(p) for p in (packages or [])]
    plan.decryption_keys = {str(k): v for k, v in (depot_keys or {}).items()}
    plan.manifest_ids = {str(k): v for k, v in (manifest_ids or {}).items()}
    plan.tokens = {str(k): v for k, v in (tokens or {}).items()}
    plan.dlc_data = {str(k): v for k, v in (dlc_data or {}).items()}
    plan.manifest_files = manifest_files or []
    return plan
