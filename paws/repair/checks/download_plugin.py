from __future__ import annotations

from ..model import Problem


def _closed_first() -> str | None:
    from ...steam import is_running

    if is_running():
        return (
            "close steam first: SLSsteam reloads plugins on any change, and doing that under a running steam is risky"
        )
    return None


def check_download_plugin() -> list[Problem]:
    """SLSsteam's download plugin is there but can't do its job: Plugins is off, the sections it reads are gone, or a
    steam update moved the code it hooks"""
    from ...sls import plugins

    plugin = plugins.downloader()
    if plugin is None:
        return []
    if not plugins.master_on():

        def turn_on() -> str:
            plugins.set_master(True)
            return "Plugins is on. restart steam through paws to load the download plugin"

        return [
            Problem(
                "plugins.download-off",
                "the download plugin is there but Plugins is off",
                f"{plugin.name} only runs with Plugins: yes, so games added for download stay at 0 B",
                "turn Plugins on (it takes effect when steam starts)",
                turn_on,
                "warn",
            )
        ]
    out = []
    missing = plugins.missing_patterns(plugin)
    if missing:

        def park() -> str:
            why = _closed_first()
            if why:
                return why + ". nothing changed"
            parked = plugins.disable(plugin.stem)
            return f"moved it to {parked.path.parent.name}. turn it back on in Plugins once there's an update"

        out.append(
            Problem(
                "plugins.download-outdated",
                f"{plugin.name} doesn't fit this steam client",
                f"{len(missing)} of its byte patterns aren't in steamclient.so any more (steam updated), so it can't "
                "hook what it needs and downloads fail. a plugin hooking the wrong spot can take steam down with it",
                "set it aside until there's an update for this steam version",
                park,
                "error",
            )
        )
    from ...config import find_config, parsed

    config_path = find_config()
    data = parsed(config_path) if config_path else {}
    absent = [k for k in sorted(plugins.DOWNLOAD_KEYS) if k not in data]
    if config_path is not None and absent:

        def add_sections() -> str:
            from ...config import fill_missing

            added = fill_missing(config_path, only=plugins.DOWNLOAD_KEYS)
            return f"added {', '.join(added) or 'nothing'} to config.yaml"

        out.append(
            Problem(
                "plugins.download-sections",
                f"config.yaml has no {' or '.join(absent)}",
                f"{plugin.name} reads its depots and keys from there and warns about it on every steam start",
                "add the empty sections (games you add fill them)",
                add_sections,
                "warn",
            )
        )
    return out
