from __future__ import annotations

_GRAD_STOPS = ("#00d0ff", "#4066ff", "#9b4dff", "#ff4da6", "#ffb84d")


def tween(t):
    t = 0.0 if t <= 0 else 1.0 if t >= 1 else t
    span = t * (len(_GRAD_STOPS) - 1)
    lo = min(int(span), len(_GRAD_STOPS) - 2)
    f = span - lo
    a, b = (_GRAD_STOPS[lo], _GRAD_STOPS[lo + 1])
    channels_a = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    channels_b = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    rgb = [round(x + (y - x) * f) for x, y in zip(channels_a, channels_b)]
    return f"#{''.join(f'{c:02x}' for c in rgb)}"


def gradient_text(text: str) -> str:
    from ... import settings

    if not text:
        return ""
    if settings.is_minimal():
        return text
    n = max(len(text) - 1, 1)
    return "".join(f"[{tween(i / n)}]{ch}[/]" for i, ch in enumerate(text))
