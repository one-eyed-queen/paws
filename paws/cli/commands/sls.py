from __future__ import annotations

import json

from ... import sls as sls_module

NAME = "sls"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="SLSsteam install/update/uninstall", parents=[common])
    p.add_argument("action", choices=["install", "update", "uninstall", "latest"], default="install", nargs="?")
    p.add_argument("--source", choices=["github", "private", "forgejo", "local"], default="github")
    p.add_argument("--tag", help="specific GitHub release tag")
    p.add_argument("--url", help="repo link (GitHub/Forgejo/GitLab/git) or .zip/.7z path for a private source")
    p.add_argument("--name", default="SLSsteam", help="what a private build is called (SLSsteam, HeadCrab)")
    p.add_argument("--no-desktop", action="store_true")


def _say(args, payload, text):
    print(json.dumps(payload) if args.json else text)


def _latest(args):
    sls = sls_module.find_sls()
    latest = sls_module.fetch_latest_github_tag()
    installed = sls_module.installed_version(sls)
    has_update = sls_module.update_available(sls, latest)
    _say(
        args,
        {"installed": installed, "latest": latest, "update_available": has_update},
        f"installed={installed or 'none'} latest={latest or '?'}" + ("  -> update available" if has_update else ""),
    )
    return 0 if latest else 1


def _uninstall(args):
    if not sls_module.uninstall(sls_module.find_sls()):
        _say(args, {"ok": False, "error": "nothing to uninstall"}, "nothing to uninstall")
        return 1
    _say(args, {"ok": True, "action": "uninstall"}, "uninstalled, config and tickets left alone")
    return 0


def run(args) -> int:
    if args.action == "latest":
        return _latest(args)
    try:
        if args.action == "uninstall":
            return _uninstall(args)
        source = sls_module.SlsSource(
            name=args.name if args.source == "private" else args.source, kind=args.source, url=args.url, tag=args.tag
        )
        result = sls_module.install_release(source, write_desktop=not args.no_desktop)
    except (sls_module.SlsError, OSError) as error:
        _say(args, {"ok": False, "error": str(error)}, f"paws sls {args.action}: {error}")
        return 1
    _say(
        args,
        {"ok": True, "action": args.action, "so": str(result.sls_so) if result and result.sls_so else None},
        "done",
    )
    return 0
