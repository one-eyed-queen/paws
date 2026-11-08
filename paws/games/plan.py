from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..manifest.bundle import ManifestBundle


def _in_library(appid: str) -> bool:
    """does steam already list this app for the signed-in user? installed counts, and so does any
    app with a block in localconfig.vdf. being offline or having no steam at all reads as "not in
    the library", which only means the game gets the AdditionalApps row it needs to show up.
    a game paws unlocked gets both of those too, so it never counts: taken for owned, it lost its
    unlock row and steam uninstalled it"""
    try:
        from ..steam.library import owned_appids

        if str(appid) not in owned_appids():
            return False
    except (ImportError, OSError):
        return False
    return str(appid) not in unlocked_by_paws()


UNLOCK_SECTIONS = ("AdditionalApps", "AdditionalPackageApps", "AdditionalPackages")


def unlocked_by_paws() -> set[str]:
    """games paws wrote an unlock row or depot keys for since they were last removed. a game you own needs neither"""
    from ..util import undo

    out, removed = set(), set()
    for record in undo.history(limit=100000):  # newest first
        detail = record.get("detail") or {}
        appid = str(detail.get("appid") or "")
        kind = record.get("kind")
        if kind == "apply_remove":
            removed.add(appid)
        if appid in removed:
            continue
        entries = (detail.get("entries") or []) if kind == "config.add" else []
        if appid and (kind == "vdf.add" or any(entry[0] in UNLOCK_SECTIONS for entry in entries if entry)):
            out.add(appid)
    return out


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
        # a game you don't own only shows up in the library because SLSsteam appends AdditionalApps
        # to the list of apps steam thinks you're subscribed to (feats/apps.cpp getSubscribedApps).
        # AppIds alone never reaches that list - it only decides what gets excluded - so a game
        # added with AppIds and no AdditionalApps silently never appears. the catch is that
        # AdditionalApps also overrides the owner id, which is what breaks downloads for a game
        # you already own or share, so it only goes in for games that aren't in your library yet.
        # private builds that read AdditionalPackageApps take the game there instead: that's their download path
        from .download import build_reads, packages_supported, reads

        package_apps = reads("AdditionalPackageApps")
        by_package = bool(self.packages) and packages_supported() and not package_apps  # games/download.py: 0 B
        if self.appid and not _in_library(self.appid):
            if package_apps:
                out.append(Change("config.yaml", "add", f"AdditionalPackageApps {self.appid}"))
            elif not by_package:
                out.append(Change("config.yaml", "add", f"AdditionalApps     {self.appid}"))
        for a in self.additional_apps:
            # AppIds is the whitelist entry the game and each of its DLC need once AdditionalApps
            # has injected it; without UseWhitelist: yes a blacklist would exclude them instead
            out.append(Change("config.yaml", "add", f"AppIds     {a}"))
        if build_reads("AdditionalPackages") and not package_apps:  # public build: does nothing there
            for p in self.packages:
                out.append(Change("config.yaml", "add", f"AdditionalPackages {p}"))
        if reads("AdditionalDepots"):  # older private builds or the download plugin: every keyed depot but the game
            for d in self.decryption_keys:
                if d != self.appid:
                    out.append(Change("config.yaml", "add", f"AdditionalDepots   {d}"))
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
    appid = str(bundle.main_appid() or "")
    plan = GamePlan(appid=appid, name=name or "")
    plan.names = {str(k): v for k, v in flat["names"].items()}
    if not appid:
        # a .manifest or a .key on its own only names its depot: ask steam which game that depot is part of
        from collections import Counter

        from ..sources.depots import owners

        placed = owners(sorted({*bundle.known_depots(), *flat["depots"]}))
        if placed:
            appid = plan.appid = Counter(game for game, _ in placed.values()).most_common(1)[0][0]
            plan.name = plan.name or next(n for game, n in placed.values() if game == appid)
    # a lua unlocker file calls addappid() for the game AND for each of its depots (that's how
    # it registers each depot's decryption key) - an id that also gets a manifest id, or that
    # arrives already carrying a decryption key, is a depot and not a real app, and must not end
    # up in AdditionalApps/AppIds (SLSsteam would try to fake ownership of a "game" that doesn't
    # exist, alongside the real one). a depot id can show up three ways: setManifestid() inside
    # the .lua, a standalone .manifest file dropped alongside it, or an AddAppID() carrying a key
    keyed_depots = {d for lm in bundle.luas for d, _, _ in lm.decryption_keys}
    depot_ids = {d for lm in bundle.luas for d, _, _ in lm.manifest_ids} | {d for d, _, _p in bundle.manifests}
    depot_ids |= keyed_depots
    # the game's own appid can legitimately appear in the keyed set (AddAppID(620, "key") on a
    # single-depot game), so it always stays a real app
    real_apps = [a for a in flat["app_ids"] if a not in depot_ids or str(a) == appid]
    plan.additional_apps = [str(a) for a in real_apps] or ([appid] if appid else [])
    plan.decryption_keys = {str(k): v for k, v in flat["depots"].items()}
    plan.manifest_files = flat["manifests"]
    # a lone .manifest file (no matching .lua dropped with it) still carries its own depot id
    # and manifest id in its filename - use that too, so ManifestIds gets written even when
    # nothing ever calls setManifestid() for it. lets .lua and .manifest files get dropped
    # separately, in any order, and still add up to the same complete result
    plan.manifest_ids.update({str(d): str(m) for d, m, _p in bundle.manifests})
    for lm in bundle.luas:
        plan.manifest_ids.update({str(d): str(m) for d, m, _ in lm.manifest_ids})
        plan.tokens.update({str(a): str(s) for a, s, _ in lm.app_tokens})
        plan.dlc_data.update({str(d): n for d, n in lm.dlc_names.items()})
    # a .lua file has no concept of a store package id at all - without one in
    # AdditionalPackages, real downloads don't work (per a private build's own guide). look it
    # up the same way the store-search "Add game" flow already gets it for free; best-effort,
    # an offline/failed lookup just leaves this the way it's always been rather than break import
    if appid:
        try:
            from ..sources import from_store

            info = from_store(appid)
            plan.packages = [str(p) for p in info.packages]
            plan.name = plan.name or plan.names.get(appid) or info.name or ""
        except Exception:
            pass
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
