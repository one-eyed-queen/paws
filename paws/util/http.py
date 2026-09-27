from __future__ import annotations

import json
import urllib.request

LIMIT = 4 * 1024 * 1024


def get(url, timeout=20, headers=None, limit=LIMIT):
    request = urllib.request.Request(url, headers={"User-Agent": "paws", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        data = reply.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{url}: the reply was way too big")
    return data


def get_text(url, **kwargs):
    return get(url, **kwargs).decode()


def get_json(url, **kwargs):
    return json.loads(get_text(url, **kwargs))
