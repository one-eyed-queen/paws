from __future__ import annotations

from dataclasses import dataclass, field

from ..util import http


class SourceError(Exception):
    pass


def get_json(url, timeout=20):
    data = http.get_json(url, timeout=timeout)
    if not isinstance(data, dict):
        raise SourceError("got something odd back")
    return data


@dataclass
class GameInfo:
    appid: str
    name: str = ""
    price: str = ""
    free: bool = False
    packages: list[str] = field(default_factory=list)
    depots: dict[str, str] = field(default_factory=dict)
    dlcs: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    dlc_names: dict[str, str] = field(default_factory=dict)
    source: str = "manual"
    depot_keys: dict[str, str] = field(default_factory=dict)
    short_description: str = ""
    about: str = ""
    developers: list[str] = field(default_factory=list)
    header_image: str = ""
    screenshots: list[str] = field(default_factory=list)
