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
    return p


def _list(args) -> int:
    found = plugins.list_plugins()
    if args.json:
        print(json.dumps([{"name": p.name, "enabled": p.enabled, **p.meta} for p in found]))
        return 0
    if not found:
        print("no plugins yet: `paws plugins new <name>` to write one, or `paws plugins import <file>`")
        return 0
    for p in found:
        state = "on " if p.enabled else "off"
        extra = f"  {p.author}" if p.author else ""
        print(f"[{state}] {p.name:24} {p.version:>8}{extra}  {p.desc}")
    print(f"\nPlugins config key is {'on' if plugins.master_on() else 'off'} (`paws plugins master on` to flip it)")
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
        else:
            return _list(args)
    except SlsError as error:
        print(f"paws: {error}", file=sys.stderr)
        return 1
    return 0
