"""background add game + config tidy, against a throwaway home with no network."""
import os, tempfile, zipfile
from pathlib import Path
from unittest import mock

home = Path(tempfile.mkdtemp())
for sub in (".config/SLSsteam/cache", ".local/share/paws", ".cache", ".steam/steam/config", ".steam/steam/steamapps"):
    (home / sub).mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(home)
os.environ["PAWS_TYPE"] = "minimal"
import yaml
from paws import config, drop, games
from paws.config.tidy import tidy, unnamed_ids, split_comment
from paws.games import background
from paws.sources import depots
from paws.sources.base import GameInfo, SourceError

P, F = 0, []
def check(n, got, want=True):
    global P
    if got == want: P += 1
    else: F.append(f"{n}: got {got!r}, want {want!r}")

cfg = home / ".config/SLSsteam/config.yaml"
BASE = """# top note
UseWhitelist: yes
AppIds:
  - 620 # 620
  - 400 # Portal
  - 999

# about packages
AdditionalPackages:
  - 7 # 7
AppTokens:
  620: 123456 # 620:123456
ManifestIds:
  621: 555 # 621
DecryptionKeys:
  621: "abc#def" # 621
AdditionalApps:
  - 400 # Portal
  # a note somebody wrote
  - 620 # 620
"""
cfg.write_text(BASE)
before = yaml.safe_load(BASE)
check("split keeps # in quotes", split_comment('  621: "a #b" # name'), ('  621: "a #b"', "name"))
check("unnamed", set(unnamed_ids()), {"620", "999", "621"})
check("tidy writes", tidy({"620": "Portal 2", "621": "Portal 2"}))
text = cfg.read_text(); after = yaml.safe_load(text)
check("sorted by name", [l.strip() for l in text.split("AppIds:\n")[1].split("\n\n")[0].splitlines()], ["- 400 # Portal", "- 620 # Portal 2", "- 999"])
check("token junk label replaced", "620: 123456 # Portal 2" in text)
check("token not echoed in a comment", "# 620:123456" not in text)
check("package does not borrow app name", "- 7\n" in text)
check("quoted # survives", after["DecryptionKeys"][621], "abc#def")
check("hand written section left alone", "  # a note somebody wrote" in text)
check("comments between sections stay", "# about packages" in text and "# top note" in text)
check("values same", after["AppIds"] != None and sorted(after["AppIds"]) == sorted(before["AppIds"]) and after["AppTokens"] == before["AppTokens"] and after["AdditionalApps"] == before["AdditionalApps"])
check("second tidy no write", tidy({"620": "Portal 2"}), False)
config.remove_rendered("AppIds", "  - 620 # 620")
check("remove_rendered ignores label", 620 not in yaml.safe_load(cfg.read_text())["AppIds"])

API = {620: {"common": {"type": "Game", "name": "Portal 2"}, "depots": {"621": {}, "622": {"depotfromapp": "1"}}},
       2855520: {"common": {"type": "DLC", "parent": "1245620"}},
       1245620: {"common": {"type": "game", "name": "ELDEN RING"}},
       228980: {"common": {"type": "config"}, "depots": {"228981": {}}}}
calls = []
def fake_app(a):
    calls.append(a); return API.get(a, {})
with mock.patch.object(depots, "_app", fake_app):
    check("depot -> game", depots.owners(["621"]), {"621": ("620", "Portal 2")})
    n = len(calls); depots.owners(["621"]); check("cached", len(calls), n)
    check("dlc id -> parent game", depots.owners(["2855520"])["2855520"], ("1245620", "ELDEN RING"))
    check("redist is no game", depots.owners(["228981"]), {})
    check("borrowed depot not owned", depots.owners(["622"]).get("622"), None)
def offline(a): raise SourceError("x")
(home / ".cache/paws/depot_owners.json").unlink()
with mock.patch.object(depots, "_app", offline):
    check("offline empty", depots.owners(["621"]), {})
with mock.patch.object(depots, "_app", fake_app):
    check("offline not remembered as a miss", depots.owners(["621"]), {"621": ("620", "Portal 2")})

store = lambda a: GameInfo(appid=a, name="Portal 2", packages=["7877"], source="store")
def bg():
    with mock.patch("paws.sources.from_store", store), mock.patch("paws.games.plan.from_store", store, create=True), \
         mock.patch("paws.sources.store.free_ids", lambda ids: set()), mock.patch("paws.games.free.free_ids", lambda ids: set(), create=True), \
         mock.patch("paws.games.apply._nudge_steam", side_effect=AssertionError("nudged")) as n:
        return background.add_missing(), n
cfg.write_text("UseWhitelist: yes\nAppIds:\nAdditionalApps:\nManifestIds:\n  621: 555 # 621\n")
added, nudge = bg()
data = yaml.safe_load(cfg.read_text())
check("start adds the game", added, ["Portal 2"])
check("AdditionalApps row (build without AdditionalPackages)", data["AdditionalApps"], [620])
check("AppIds row", data["AppIds"], [620])
check("package row", data["AdditionalPackages"], [7877])
check("named", "- 620 # Portal 2" in cfg.read_text())
check("no download nudge", nudge.called, False)
check("no second add", bg()[0], [])
games.apply_remove(games.plan_remove("620"))
data = yaml.safe_load(cfg.read_text())
check("removed", 620 in (data.get("AdditionalApps") or []), False)
if not (data.get("ManifestIds") or {}):
    cfg.write_text(cfg.read_text().replace("ManifestIds:", "ManifestIds:\n  621: 555"))
check("removed game stays removed", bg()[0], [])
(home / ".config/paws/bg_add_skip.json").unlink()
sfile = home / ".steam/steam/config/localconfig"  # owned game is not missing
with mock.patch("paws.games.background._in_library", lambda a: True):
    check("owned is not missing", background.missing_games(), {})

# drops
cfg.write_text("UseWhitelist: yes\nAppIds:\nAdditionalApps:\nManifestIds:\nDecryptionKeys:\n")
work = Path(tempfile.mkdtemp())
m = work / "621_555.manifest"; m.write_bytes(b"x")
def dropit(paths):
    with mock.patch("paws.sources.from_store", store), mock.patch("paws.sources.store.free_ids", lambda ids: set()), \
         mock.patch("paws.games.free.free_ids", lambda ids: set(), create=True), mock.patch.object(depots, "_app", fake_app), \
         mock.patch("paws.games.apply._nudge_steam", lambda a: False):
        return drop.import_files(paths)
r = dropit([m]); data = yaml.safe_load(cfg.read_text())
check("manifest drop title", r.title, "added Portal 2")
check("manifest drop adds game", (data["AppIds"], data["AdditionalPackages"]), ([620], [7877]))
cfg.write_text("UseWhitelist: yes\nAppIds:\nAdditionalApps:\nManifestIds:\nDecryptionKeys:\n")
k = work / "621.key"; k.write_text("a" * 64)
r = dropit([k]); data = yaml.safe_load(cfg.read_text())
check("named key drop adds game", (data["AppIds"], data["AdditionalPackages"]), ([620], [7877]))
check("named key stored", data["DecryptionKeys"], {621: "a" * 64})
cfg.write_text("UseWhitelist: yes\nAppIds:\nAdditionalApps:\nManifestIds:\nDecryptionKeys:\n")
k2 = work / "keys.key"; k2.write_text(f"621;{'b'*64}\n")
z = work / "bundle.zip"
with zipfile.ZipFile(z, "w") as f: f.write(k2, "keys.key")
check("key zip recognised", drop.dropped_files(str(z)), [z])
r = dropit([z]); data = yaml.safe_load(cfg.read_text())
check("zipped depot;key adds game", (data["AppIds"], data["AdditionalPackages"]), ([620], [7877]))
import shutil, subprocess
if shutil.which("7z"):
    seven = work / "b.7zip"; subprocess.run(["7z", "a", "-t7z", str(seven), str(k2)], capture_output=True)
    check(".7zip recognised", drop.dropped_files(str(seven)), [seven])
cfg.write_text("UseWhitelist: yes\nAppIds:\nAdditionalApps:\nManifestIds:\nDecryptionKeys:\n")
r = dropit([work / "k.key"] if False else [k2.with_name("nope.key")]) if False else None
print("passed:", P); print("failed:", len(F))
for f in F: print("  -", f)
raise SystemExit(bool(F))
