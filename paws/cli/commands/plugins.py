from __future__ import annotations

import json
import sys

from ...sls import SlsError, plugins

NAME = "plugins"


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        NAME, help="SLSsteam plugins / add-ons: list, write, import, export, enable, disable", parents=[common]
    )
    sp = p.add_subparsers(dest="plugins_command")

    new = sp.add_parser("new", parents=[common], help="start a new plugin from a template")
    new.add_argument("name")
    new.add_argument("--author", default="")
    new.add_argument("--version", dest="plugin_version", default="1.0.0", metavar="VERSION")
    new.add_argument("--desc", default="")
    new.add_argument("--enable", action="store_true", help="put it straight in SLSsteam's live plugins folder")

    for action in ("enable", "disable", "remove"):
        one = sp.add_parser(action, parents=[common])
        one.add_argument("name")

    imp = sp.add_parser("import", parents=[common], help="add a .lua file or a .paws-plugin.zip")
    imp.add_argument("path")
    imp.add_argument("--enable", action="store_true")

    exp = sp.add_parser("export", parents=[common], help="pack a plugin into a .paws-plugin.zip")
    exp.add_argument("name")
    exp.add_argument("--to", default=".", help="folder to write it into (default: here)")

    master = sp.add_parser("master", parents=[common], help="the Plugins config key: on/off for all of them at once")
    master.add_argument("state", nargs="?", choices=["on", "off"])

    download = sp.add_parser(
        "download",
        parents=[common],
        help="add SLSsteam's download plugin, so the public build downloads games with their real size",
    )
    download.add_argument("--remove", action="store_true", help="set it aside again (it goes to plugins-disabled)")

    available = sp.add_parser(
        "available", parents=[common], help="list the optional plugins published for this steam / SLSsteam build"
    )
    available.add_argument("--refresh", action="store_true", help="ignore the local manifest cache")

    install = sp.add_parser("install", parents=[common], help="install one optional plugin from the public collection")
    install.add_argument("name")
    install.add_argument("--refresh", action="store_true", help="ignore the local manifest cache")
    return p


def _download(args) -> int:
    if args.remove:
        result = plugins.remove_download()
        text = f"set aside: {result['removed']}" if result["removed"] else "the download plugin isn't installed"
    else:
        result = plugins.install_download()
        arch = plugins.arch_report()
        text = f"installed {result['path']}"
        text += f"\nsteam {arch['steam_arch'] or '?'}-bit / SLSsteam {arch['sls_arch'] or '?'}-bit detected"
        if result.get("source") == "remote":
            text += (
                f"\nplugin {result.get('plugin_version') or '?'} from the public plugin collection "
                f"(steam {result.get('steam_arch')}-bit build {result.get('steam_build')}, "
                f"SLS {result.get('sls_version')})"
            )
        else:
            text += "\nbundled 32-bit plugin (no version match available, offline fallback)"
        if result["plugins_turned_on"]:
            text += "\nPlugins was off, it's on now"
        if result["updates_turned_on"]:
            text += "\nDisableUpdates is off now: with it on, steam shows 0 B next to these games instead of their size"
        if result["sections_added"]:
            text += f"\nadded {', '.join(result['sections_added'])} to config.yaml"
        if result["restart_steam"]:
            text += "\nsteam is running: restart it (through paws or the SLSsteam launcher) to load the plugin"
        else:
            text += "\nstart steam through paws (or the SLSsteam launcher) to load it"
    print(json.dumps(result) if args.json else text)
    return 0


def _available(args) -> int:
    found = plugins.collection_plugins(refresh=args.refresh)
    if args.json:
        print(json.dumps(found))
        return 0
    if not found:
        print("the public plugin collection has no optional plugins listed yet")
        return 0
    for entry in found:
        state = "installed" if entry["installed"] else "available"
        arch = entry.get("steam_arch") or "?"
        print(f"{entry['name']:14} {state:9} {arch}-bit  {entry.get('version', ''):20} {entry.get('desc', '')}")
    print("install one with: paws plugins install <name>")
    return 0


def _install(args) -> int:
    result = plugins.install_collection(args.name, refresh=args.refresh)
    text = f"installed {result['name']} {result['version']} -> {result['path']}"
    print(json.dumps(result) if args.json else text)
    return 0


def _list(args) -> int:
    found = plugins.list_plugins()
    if args.json:
        print(json.dumps([{"name": p.name, "enabled": p.enabled, **p.meta} for p in found]))
        return 0
    if not found:
        print("no plugins yet: `paws plugins new <name>` to write one, or `paws plugins import <file>`")
        print("on the public build games stay at 0 B without the download plugin: `paws plugins download` adds it")
        return 0
    loader = plugins.downloader()
    for p in found:
        state = "on " if p.enabled else "off"
        extra = f"  {p.author}" if p.author else ""
        role = ""
        if loader is not None and p.path == loader:
            missing = plugins.missing_patterns(loader)
            role = "  (does downloads" + (", doesn't fit this steam client)" if missing else ")")
        print(f"[{state}] {p.name:24} {p.version:>8}{extra}  {p.desc}{role}")
    print(f"\nPlugins config key is {'on' if plugins.master_on() else 'off'} (`paws plugins master on` to flip it)")
    if loader is None:
        print("no download plugin: on the public build games stay at 0 B. `paws plugins download` adds it")
    return 0


def run(args) -> int:
    action = getattr(args, "plugins_command", None)
    try:
        if action == "new":
            made = plugins.new_plugin(args.name, args.author, args.plugin_version, args.desc, enabled=args.enable)
            print(f"wrote {made.path}")
        elif action == "enable":
            plugins.enable(args.name)
            print(f"{args.name}: on")
        elif action == "disable":
            plugins.disable(args.name)
            print(f"{args.name}: off")
        elif action == "remove":
            print(plugins.remove(args.name))
        elif action == "import":
            got = plugins.import_plugin(args.path, enabled=args.enable)
            print(f"imported {got.name} ({'on' if got.enabled else 'off'})")
        elif action == "export":
            print(plugins.export_plugin(args.name, args.to))
        elif action == "master":
            if args.state is not None:
                plugins.set_master(args.state == "on")
            print("Plugins:", "on" if plugins.master_on() else "off")
        elif action == "download":
            return _download(args)
        elif action == "available":
            return _available(args)
        elif action == "install":
            return _install(args)
        else:
            return _list(args)
    except SlsError as error:
        print(f"paws: {error}", file=sys.stderr)
        return 1
    return 0
