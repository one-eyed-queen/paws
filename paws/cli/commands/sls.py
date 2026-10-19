from __future__ import annotations

import json
from pathlib import Path

from ... import sls as sls_module

NAME = "sls"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="SLSsteam install/update/uninstall", parents=[common])
    p.add_argument("action", choices=["install", "update", "uninstall", "latest"], default="install", nargs="?")
    p.add_argument("--source", choices=["github", "private", "forgejo", "local"], default="github")
    p.add_argument("--tag", help="specific GitHub release tag")
    p.add_argument(
        "--variant", choices=["any", "arch"], default="any", help="github only: the portable .7z or the arch package"
    )
    p.add_argument(
        "--flavour", choices=["release", "debug"], default="release", help="github only: release or debug build"
    )
    p.add_argument("--url", help="repo link (GitHub/Forgejo/GitLab/git) or .zip/.7z path for a private source")
    p.add_argument("--name", default="SLSsteam", help="what a private build is called (SLSsteam, HeadCrab)")
    p.add_argument("--no-desktop", action="store_true")
    p.add_argument(
        "--purge",
        action="store_true",
        help="uninstall only: also remove a package-managed copy (needs sudo) and set the config aside",
    )
    p.add_argument(
        "--allow-unverified",
        action="store_true",
        help="windows only: run a HubCapTools build paws has no checksum for",
    )


def _say(args, payload, text):
    print(json.dumps(payload) if args.json else text)


def _latest(args):
    sls = sls_module.find_sls()
    latest = sls_module.fetch_latest_github_tag()
    installed = sls_module.installed_version(sls)
    state = sls_module.update_state(sls, latest)
    _say(
        args,
        {
            "installed": installed,
            "latest": latest,
            "state": state,
            "update_available": sls_module.update_available(sls, latest),
            "why": sls_module.update_reason(sls, latest),
        },
        f"installed={installed or 'none'} latest={latest or '?'}  -> {state}: {sls_module.update_reason(sls, latest)}",
    )
    # only 0 when we actually know. "can't tell" used to exit 0 and read as a clean bill of health
    return 0 if state in (sls_module.NO, sls_module.YES) else 1


def _uninstall(args):
    sls = sls_module.find_sls()
    report = sls_module.uninstall(sls, purge=getattr(args, "purge", False))
    removed = report.get("removed", [])
    kept = report.get("kept", [])
    failed = report.get("failed", [])
    if not removed and not failed:
        _say(args, {"ok": False, "removed": False, "kept": kept}, "nothing was removed")
        return 1
    lines = (["removed SLSsteam:"] + [f"  {r}" for r in removed]) if removed else ["nothing was removed"]
    if report.get("config_backup"):
        lines.append(f"  config kept at {report['config_backup']} (moved aside, not deleted)")
    lines.append("steam itself was not touched.")
    if kept:
        lines += ["", "left alone (they need root):"] + [f"  {k}" for k in kept]
    if failed:
        lines += ["", "could not finish:"] + [f"  {f}" for f in failed]
    _say(
        args,
        {
            "ok": not failed,  # a copy left for root (pacman) isn't a failed uninstall, it's reported in "kept"
            "removed": bool(removed),
            "items": removed,
            "kept": kept,
            "failed": failed,
            "config_backup": report.get("config_backup"),
        },
        "\n".join(lines),
    )
    return 0 if not failed else 1


def run(args) -> int:
    if args.action == "latest":
        return _latest(args)
    before = sls_module.find_sls()
    before_version = sls_module.installed_version(before)
    try:
        if args.action == "uninstall":
            return _uninstall(args)
        if args.action == "update" and args.source == "github" and not args.tag:
            # say up front when there is nothing to do, instead of downloading the same bytes
            # again and reporting a cheerful "done"
            latest = sls_module.fetch_latest_github_tag()
            state = sls_module.update_state(before, latest)
            if state == sls_module.NO:
                _say(
                    args,
                    {"ok": True, "action": "update", "changed": False, "why": sls_module.update_reason(before, latest)},
                    f"already up to date ({sls_module.update_reason(before, latest)})",
                )
                return 0
            if state == sls_module.UNKNOWN and args.json:
                _say(
                    args,
                    {"ok": True, "action": "update", "changed": None, "why": sls_module.update_reason(before, latest)},
                    f"can't compare versions, fetching the newest github build anyway ({sls_module.update_reason(before, latest)})",
                )
        source = sls_module.SlsSource(
            name=args.name if args.source == "private" else args.source,
            kind=args.source,
            url=args.url,
            tag=args.tag,
            variant=args.variant,
            flavour=args.flavour,
        )
        result, wired = sls_module.install_release(
            source, write_desktop=not args.no_desktop, allow_unverified=args.allow_unverified
        )
    except (sls_module.SlsError, OSError) as error:
        _say(args, {"ok": False, "error": str(error)}, f"paws sls {args.action}: {error}")
        return 1
    so = result.sls_so if result else None
    # verify rather than trust: no library on disk means nothing happened, and reporting ok for
    # that is what made "update" look like it worked when it never touched anything
    if not so or not Path(so).exists():
        _say(
            args,
            {"ok": False, "action": args.action, "changed": False, "error": "nothing was written"},
            f"paws sls {args.action}: nothing was written (no built library in that file)",
        )
        return 1
    after_version = sls_module.installed_version(sls_module.find_sls())
    # a launcher pointing at files that aren't there is the failure that reads as "install did
    # something". say so instead of reporting a cheerful ok.
    broken = [str(p) for p in wired if not Path(p).is_file()]
    if not args.no_desktop and not wired:
        broken = ["no usable library to inject (steam will start without SLSsteam)"]
    left = sls_module.other_installs(keep=result.lib_dir if result else None)
    payload = {
        "ok": not broken,
        "action": args.action,
        "changed": after_version != before_version,
        "so": str(so),
        "version": after_version,
        "wired": [str(p) for p in wired],
        "other_installs": left,
    }
    if broken:
        payload["error"] = "; ".join(broken)
    lines = [
        f"{args.action}: {before_version} -> {after_version}"
        if after_version != before_version
        else f"{args.action}: {after_version}"
    ]
    if wired:
        lines.append("injected: " + ":".join(str(p) for p in wired))
    if broken:
        lines += ["PROBLEM: " + b for b in broken]
    if left:
        lines += ["also installed: " + line for line in left]
    _say(args, payload, "\n".join(lines))
    return 0 if not broken else 1
