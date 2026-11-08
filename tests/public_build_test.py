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
for _k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
    os.environ.pop(_k, None)  # paws puts SLSsteam's config under XDG_CONFIG_HOME, which would be the real one
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

# ---- the public build + SLSsteam's download plugin ---------------------------------------------
import hashlib, struct
from paws.repair.checks import check_download_plugin, check_launcher_quoting, check_public_build
from paws.sls import SlsError, desktop, plugins
from paws.sls.install import bits_problem
from paws.util import elf


def fake_elf(code: bytes, bits: int = 32) -> bytes:
    """a library with just a .text and its name table, enough for elf.bits / elf.code"""
    names = b"\0.text\0.shstrtab\0"
    if bits == 32:
        size, entry = 52, 40
        pack = lambda *f: struct.pack("<IIIIIIIIII", *f)
        head = struct.pack("<HHIIIIIHHHHHH", 3, 3, 1, 0, 0, size + len(code) + len(names), 0, size, 0, 0, entry, 3, 2)
    else:
        size, entry = 64, 64
        pack = lambda *f: struct.pack("<IIQQQQIIQQ", *f)
        head = struct.pack("<HHIQQQIHHHHHH", 3, 62, 1, 0, 0, size + len(code) + len(names), 0, size, 0, 0, entry, 3, 2)
    table = pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0) + pack(1, 1, 0, 0, size, len(code), 0, 0, 1, 0)
    table += pack(7, 3, 0, 0, size + len(code), len(names), 0, 0, 1, 0)
    return b"\x7fELF" + bytes([1 if bits == 32 else 2, 1, 1]) + bytes(9) + head + code + names + table


STUB = (
    b'local hit = memhlp.patternScan("E8 ? ? ? ? 83 C4", steamClientMod)\n'
    b'Downloader.AdditionalDepots = SLS.config:getIntList("AdditionalDepots")\n'
    b'local keyNode = SLS.config:getNode("DecryptionKeys")\n'
    b"-- hooks GetManifestRequestCode\n"
)
client = home / ".steam/steam/ubuntu12_32/steamclient.so"
client.parent.mkdir(parents=True, exist_ok=True)
client.write_bytes(fake_elf(b"\x90\xe8\x01\x02\x03\x04\x83\xc4\x90"))
check("elf: 32-bit", elf.bits(client), 32)
check("elf: finds the pattern in .text", elf.matches("E8 ? ? ? ? 83 C4", elf.code(client)), 1)
check("elf: not a pattern that isn't there", elf.matches("E8 ? ? 90 90", elf.code(client)), 0)

cfg.write_text(
    "UseWhitelist: yes\nPlugins: no\nDisableUpdates: yes\nAppIds:\n  - 620 # Portal 2\nAdditionalApps:\n  - 620 # Portal 2\nManifestIds:\n"
)
check("no plugin: can't download", download.can_download(), False)
told = check_public_build(cfg)
check("no plugin: the 0 B notice names the plugin", bool(told) and "paws plugins download" in told[0].fix_note)
check("no plugin: paws never adds it by itself", bool(told) and told[0].fix is None)

with mock.patch("paws.steam.is_running", lambda: True):  # Plugins is off: staged, loads at the next start
    try:
        plugins.install_download(data=STUB)
        check("a file that isn't the checked download.lua is refused", "installed", "refused")
    except SlsError:
        check("a file that isn't the checked download.lua is refused", True)
    with mock.patch.object(plugins, "DOWNLOAD_SHA256", hashlib.sha256(STUB).hexdigest()):
        result = plugins.install_download(data=STUB)
        try:
            plugins.install_download(data=STUB)
            check("Plugins on + steam running: not written into a live steam", "installed", "refused")
        except SlsError:
            check("Plugins on + steam running: not written into a live steam", True)
installed = plugins.plugins_dir() / "download.lua"
check("plugin written", installed.read_bytes(), STUB)
check("plugin file is owner only", oct(installed.stat().st_mode & 0o777), "0o600")
check("plugins folder is owner only", oct(installed.parent.stat().st_mode & 0o777), "0o700")
check("Plugins turned on", result["plugins_turned_on"] and plugins.master_on())
check("steam running: told to restart it", result["restart_steam"])
check("DisableUpdates turned off", result["updates_turned_on"] and yaml.safe_load(cfg.read_text())["DisableUpdates"], False)
check("only the plugin's sections added", sorted(result["sections_added"]), ["AdditionalDepots", "DecryptionKeys"])
check("still a public build", download.packages_supported(), False)
check("downloads through the plugin", download.plugin_downloads() and download.can_download())
check("plugin keys count as read", [download.build_reads(k) for k in ("AdditionalDepots", "DecryptionKeys")], [True, True])
check("private-build keys still unread", download.build_reads("AdditionalPackageApps"), False)
check("plugin patterns fit this client", plugins.missing_patterns(installed), [])
check("no 0 B notice with the plugin", check_public_build(cfg), [])
check("a healthy plugin is no problem", check_download_plugin(), [])
from paws.repair.checks.apps import check_disable_updates_0b

check("DisableUpdates off: no 0 B warning", check_disable_updates_0b(cfg), [])
cfg.write_text(cfg.read_text().replace("DisableUpdates: no", "DisableUpdates: yes"))
again = check_disable_updates_0b(cfg)
check("DisableUpdates back on with the plugin: 0 B warning", [p.id for p in again], ["config.disable-updates-0b"])
with mock.patch("paws.util.backup.backup_file", lambda p: None):
    again[0].fix()
check("0 B warning fix turns it off", yaml.safe_load(cfg.read_text())["DisableUpdates"], False)

cfg.write_text(cfg.read_text().replace("AdditionalDepots:\n", "AdditionalDepots:\n  - 621 # Portal 2\n"))
cfg.write_text(cfg.read_text().replace("DecryptionKeys:\n", 'DecryptionKeys:\n  621: "' + "c" * 64 + '" # Portal 2\n'))
with mock.patch("paws.util.backup.backup_file", lambda p: None):
    gone = download.drop_private_sections(cfg)
data = yaml.safe_load(cfg.read_text())
check("cleanup keeps what the plugin reads", gone, [])
check("plugin's depots kept", data.get("AdditionalDepots"), [621])

from paws.games.plan import GamePlan
plan = GamePlan(appid="620", name="Portal 2", additional_apps=["620"], decryption_keys={"620": "a" * 64, "621": "c" * 64})
with mock.patch("paws.games.plan._in_library", lambda a: False):
    rows = [c.detail.split() for c in plan.changes() if c.target == "config.yaml"]
check("plugin: game stays in AdditionalApps", ["AdditionalApps", "620"] in rows)
check("plugin: keyed depots in AdditionalDepots", ["AdditionalDepots", "621"] in rows)
check("plugin: never the game itself in AdditionalDepots", ["AdditionalDepots", "620"] in rows, False)
check("plugin: no private-build rows", [r for r in rows if r[0] in ("AdditionalPackageApps", "AdditionalPackages")], [])

client.write_bytes(fake_elf(b"\x90\x90\x90\x90"))
outdated = check_download_plugin()
check("steam update: plugin flagged", [p.id for p in outdated], ["plugins.download-outdated"])
with mock.patch("paws.steam.is_running", lambda: True):
    check("steam update: not set aside under a running steam", "close steam" in outdated[0].fix())
with mock.patch("paws.steam.is_running", lambda: False):
    outdated[0].fix()
check("steam update: set aside", installed.exists(), False)
check("steam update: kept in plugins-disabled", (plugins.disabled_dir() / "download.lua").exists())
check("set aside: no downloads", download.plugin_downloads(), False)
client.write_bytes(fake_elf(b"\x90\xe8\x01\x02\x03\x04\x83\xc4\x90"))
plugins.enable("download")
plugins.set_master(False)
off = check_download_plugin()
check("plugin but Plugins off: flagged", [p.id for p in off], ["plugins.download-off"])
off[0].fix()
check("plugin but Plugins off: fix turns it on", plugins.master_on())
with mock.patch("paws.steam.is_running", lambda: True):
    try:
        plugins.remove_download()
        check("no removing under a running steam", "removed", "refused")
    except SlsError:
        check("no removing under a running steam", True)
with mock.patch("paws.steam.is_running", lambda: False):
    check("remove sets it aside", plugins.remove_download()["removed"], str(plugins.disabled_dir() / "download.lua"))

lib64 = work / "SLSsteam64.so"
lib64.write_bytes(fake_elf(b"\x90", bits=64))
lib32 = work / "SLSsteam32.so"
lib32.write_bytes(fake_elf(b"\x90"))
check("a 64-bit SLSsteam for a 32-bit client is refused", "64-bit build" in (bits_problem(lib64) or ""))
check("a 32-bit SLSsteam is fine", bits_problem(lib32), None)

# ---- launchers: LD_AUDIT quoted the desktop entry spec's way -----------------------------------
check("plain path goes in bare", desktop.audit_arg(["/a/SLSsteam.so"]), "LD_AUDIT=/a/SLSsteam.so")
check("a path with a space quotes the whole argument", desktop.audit_arg(["/home/a b/SLSsteam.so"]), '"LD_AUDIT=/home/a b/SLSsteam.so"')
odd = desktop.audit_arg(['/q"q/x.so'])
check("quote in a path round-trips", desktop.audit_values(f"Exec=env {odd} steam %U"), ['/q"q/x.so'])
apps = home / ".local/share/applications"
apps.mkdir(parents=True, exist_ok=True)
(apps / "SLSsteam.desktop").write_text('[Desktop Entry]\nName=SLSsteam\nExec=env LD_AUDIT="/a/SLSsteam.so" /usr/bin/steam %U\n')
quoting = check_launcher_quoting(apps)
check("old mid-argument quote flagged, SLSsteam.desktop included", [p.id for p in quoting], ["launcher.quoting"])
with mock.patch("paws.util.backup.backup_file", lambda p: None):
    quoting[0].fix()
check("requoted", "Exec=env LD_AUDIT=/a/SLSsteam.so /usr/bin/steam %U" in (apps / "SLSsteam.desktop").read_text())
check("nothing left to requote", check_launcher_quoting(apps), [])
check("targets still read after requote", desktop.launcher_targets(apps), [(apps / "SLSsteam.desktop", ["/a/SLSsteam.so"])])

# ---- steam running without SLSsteam: purchase prompts, 0 B, uninstalls at start -------------------------------
import subprocess, sys
from paws.repair.checks import check_steam_without_sls
from paws.repair.checks.launchers import load_failure
from paws.steam.launch import sls_injected as injected_now

so_path = "/home/u/.local/share/SLSsteam/SLSsteam.so"
helper = f"ERROR: ld.so: object '{so_path}' cannot be loaded as audit interface: wrong ELF class: ELFCLASS32; ignored.\n"
check("64-bit helpers turning it down is normal", load_failure(helper * 3), None)
wrong = f"ERROR: ld.so: object '{so_path}' cannot be loaded as audit interface: wrong ELF class: ELFCLASS64; ignored.\n"
check("a 64-bit build is named", load_failure(helper + wrong), f"wrong ELF class: ELFCLASS64 ({so_path})")
quoted = f"ERROR: ld.so: object '\"{so_path}\"' cannot be loaded as audit interface: cannot open shared object file; ignored.\n"
check("a quoted path is named", "cannot open shared object file" in (load_failure(quoted) or ""))
logs = home / ".steam/steam/logs"
logs.mkdir(parents=True, exist_ok=True)
(logs / "console-linux.txt").write_text(helper + wrong)
with mock.patch("paws.steam.is_running", lambda: True), mock.patch("paws.steam.launch.sls_injected", lambda: False):
    found = check_steam_without_sls()
check("steam without SLSsteam flagged", [p.id for p in found], ["steam.sls-not-loaded"])
check("and the loader's reason is in it", bool(found) and "ELFCLASS64" in found[0].detail)
with mock.patch("paws.steam.is_running", lambda: True), mock.patch("paws.steam.launch.sls_injected", lambda: True):
    check("steam with SLSsteam loaded is fine", check_steam_without_sls(), [])

asked = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(20)"],
    env={**os.environ, "LD_AUDIT": str(work / "missing" / "SLSsteam.so")},
    stderr=subprocess.DEVNULL,
)
try:
    import time

    for _ in range(40):  # until the child has exec'd: before that /proc shows the parent's environment
        if b"LD_AUDIT" in Path(f"/proc/{asked.pid}/environ").read_bytes():
            break
        time.sleep(0.05)
    check("the child really asks for SLSsteam", b"SLSsteam" in Path(f"/proc/{asked.pid}/environ").read_bytes())
    with mock.patch("paws.steam.process.steam_pids", lambda: [asked.pid]), mock.patch(
        "paws.steam.process.helper_pids", lambda: []
    ):
        check("LD_AUDIT asked for but not loaded doesn't count as injected", injected_now(), False)
finally:
    asked.kill()

patch_sls.stop()
print("passed:", P)
print("failed:", len(F))
for f in F: print("  -", f)
