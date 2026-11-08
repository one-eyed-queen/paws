"""public SLSsteam: no private-only sections written, the game goes in through AdditionalApps + AppIds, keys go to
steam's config.vdf and paws' own store. a throwaway home, no network, a real SLSsteam .so stand-in without the keys."""
import os, tempfile, zipfile
from pathlib import Path
from unittest import mock

home = Path(tempfile.mkdtemp())
for sub in (".config/SLSsteam", ".local/share/SLSsteam", ".cache", ".steam/steam/config", ".steam/steam/steamapps", ".steam/steam/depotcache"):
    (home / sub).mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(home)
os.environ["PAWS_TYPE"] = "minimal"
import yaml
from paws import drop
from paws.config.seed import default_config_text, missing_keys
from paws.games import download
from paws.sources import depots
from paws.sources.base import GameInfo
from paws.steam import sync

P, F = 0, []
def check(n, got, want=True):
    global P
    if got == want: P += 1
    else: F.append(f"{n}: got {got!r}, want {want!r}")

so = home / ".local/share/SLSsteam/SLSsteam.so"
so.write_bytes(b"\0AdditionalApps\0AppIds\0ManifestIds\0DisableUpdates\0")  # what the public build's binary has
fake_sls = mock.Mock(sls_so=so, lib_dir=so.parent, kind="native")
patch_sls = mock.patch("paws.sls.find.find_sls", lambda *a, **k: fake_sls)
patch_sls.start()

check("public build detected", download.packages_supported(), False)
check("private keys unread", [download.build_reads(k) for k in download.PRIVATE_ONLY], [False] * len(download.PRIVATE_ONLY))
check("shared keys read", download.build_reads("AppIds"))
text = default_config_text()
check("fresh config has no private sections", [k for k in download.PRIVATE_ONLY if f"\n{k}:" in text], [])

cfg = home / ".config/SLSsteam/config.yaml"
cfg.write_text("UseWhitelist: yes\nAppIds:\nAdditionalApps:\nManifestIds:\n")
check("fill adds no private sections", [k for k in missing_keys(cfg) if k in download.PRIVATE_ONLY], [])
(home / ".steam/steam/config/config.vdf").write_text('"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t}\n\t\t}\n\t}\n}\n')

work = Path(tempfile.mkdtemp())
lua = work / "620.lua"
lua.write_text('addappid(620)\naddappid(621, 1, "' + "c" * 64 + '")\nsetManifestid(621, "555")\n')
man = work / "621_555.manifest"; man.write_bytes(b"m")
z = work / "620.zip"
with zipfile.ZipFile(z, "w") as f:
    f.write(lua, "620.lua"); f.write(man, "621_555.manifest")
store = lambda a: GameInfo(appid=a, name="Portal 2", packages=["7877"], source="store")
fake_app = lambda a: {"common": {"type": "game", "name": "Portal 2"}, "depots": {"621": {}}} if str(a) == "620" else None
with mock.patch("paws.sources.from_store", store), mock.patch("paws.sources.store.free_ids", lambda ids: set()), \
     mock.patch("paws.games.free.free_ids", lambda ids: set(), create=True), mock.patch.object(depots, "_app", fake_app), \
     mock.patch("paws.games.apply._nudge_steam", lambda a: False), mock.patch("paws.steam.is_running", lambda: False):
    r = drop.import_files([z])
data = yaml.safe_load(cfg.read_text())
check("drop ok", r.ok)
check("game in AppIds", 620 in (data.get("AppIds") or []))
check("game in AdditionalApps", data.get("AdditionalApps"), [620])
check("no private sections written", [k for k in download.PRIVATE_ONLY if k in data], [])
check("key in steam's config.vdf", "c" * 64 in (home / ".steam/steam/config/config.vdf").read_text())
check("key in paws' store", sync.stored_keys().get("621"), "c" * 64)
check("manifest in depotcache", (home / ".steam/steam/depotcache/621_555.manifest").exists())
check("names on rows", "# Portal 2" in cfg.read_text())

cfg.write_text(cfg.read_text() + "\nAdditionalPackages:\n  - 7877 # Portal 2\n\nDecryptionKeys:\n  622: \"" + "d" * 64 + "\" # Portal 2\n\n# inventory item list\nInventoryItems:\n")
with mock.patch("paws.util.backup.backup_file", lambda p: None):
    gone = download.drop_private_sections(cfg)
data = yaml.safe_load(cfg.read_text())
check("cleanup removes private sections", sorted(gone), ["AdditionalPackages", "DecryptionKeys", "InventoryItems"])
check("cleanup keeps the rest", data.get("AdditionalApps"), [620])
check("cleanup keeps the keys", sync.stored_keys().get("622"), "d" * 64)
check("cleanup leaves no comment behind", "inventory item list" in cfg.read_text(), False)

patch_sls.stop()
print("passed:", P)
print("failed:", len(F))
for f in F: print("  -", f)
